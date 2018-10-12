import argparse
import sys
import gym
import numpy as np
from itertools import count

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
from torch.distributions import Categorical

# Grid world helpers
from helpers import VISIBLE_RADIUS, Grid, Agent, Environment

# Boat race helpers
from boat_race import make_game

parser = argparse.ArgumentParser(description='PyTorch REINFORCE example')
parser.add_argument('--gamma', type=float, default=0.99, metavar='G',
                    help='discount factor (default: 0.99)')
parser.add_argument('--seed', type=int, default=543, metavar='N',
                    help='random seed (default: 543)')
parser.add_argument('--render', action='store_true',
                    help='render the environment')
parser.add_argument('--log_interval', type=int, default=1, metavar='N',
                    help='interval between training status logs (default: 10)')
args = parser.parse_args()

# select the environment

#####
## use cartpole
# env = gym.make('CartPole-v0')
# env_boat_race = False
# env.seed(args.seed)
# reward_threshold = env.spec.reward_threshold
# input_size = 4
# output_size = 2
# env_max_steps = 10000

####### GRID WORLD
# use the gridworld environment
# env = Environment()
# env_boat_race = False
# visible_squares = (VISIBLE_RADIUS * 2 + 1) ** 2
# # Plus agent health, y, x
# input_size = visible_squares + 1 + 2 
# # For both action and expected value
# output_size = 4+1
# reward_threshold = 200000 # env.spec.reward_threshold
# env_max_steps = 10000

### BOAT RACE
game, board, reward, discount = make_game()
env_boat_race = True
input_size = board.layered_board.view(-1).shape[0]
output_size = 5
env_max_steps = 101
reward_threshold = 200000 # env.spec.reward_threshold

torch.manual_seed(args.seed)


class Policy(nn.Module):
    def __init__(self, input_size, hidden_size, output_size):
        super(Policy, self).__init__()
        self.affine1 = nn.Linear(input_size, hidden_size)
        self.affine2 = nn.Linear(hidden_size, output_size)

        self.saved_log_probs = []
        self.rewards = []

    def forward(self, x):
        # print('step0', x)
        # x = F.tanh(x) # Squash inputs
        # print('step1', x)
        x = self.affine1(x)
        # print('step2', x)
        x = F.relu(x)
        # print('step3', x)
        x = self.affine2(x)
        # print('step4', x)
        action_scores = F.softmax(x, dim=0)
        # print('step5', action_scores)
        return action_scores

hidden_size = 32
learning_rate = 3e-2
policy = Policy(input_size=input_size,
                hidden_size=hidden_size,
                output_size=output_size)
optimizer = optim.Adam(policy.parameters(), lr=learning_rate)
eps = np.finfo(np.float32).eps.item()


def select_action(state):
    if env_boat_race:
        # action space is a 1x5 list of binary actions
        # the actions are defined as follows: [left, right, up, down, stay]
        # the action dynamics are defined further in AgentDrape update
        probs = policy(Variable(state))

        # POLICY BASED ACTION
        # m = Categorical(probs)
        # selected_action = m.sample()
        # need to return action as a tensor
        # action = torch.Tensor([0,0,0,0,0])
        # action[selected_action.data] = 1
        # log_prob = m.log_prob(selected_action)

        # RANDOM POLICY
        m = Categorical(probs)
        selected_action = m.sample()
        action = torch.Tensor([0,0,0,0,0])
        action[np.random.randint(0, high=5)] = 1
        log_prob = m.log_prob(selected_action)

        # ORIGINAL BOAT RACE EXAMPLE
        # print('probs', probs, action)
        # compute the cumulative distribution
        # cdist = probs.cumsum(0)
        # print('cdist', cdist)
        # computer the t-distribution by comprate with random sample
        # tdist = (probs > torch.rand(1)[0]).float()
        # print('tdist', tdist.data)
        # action is calculated as the t-distribution minus the rearranged
        # print('rearrange', torch.cat([torch.zeros(1), tdist.data[:-1]]))
        # action = tdist.data - torch.cat([tdist.data[:-1], torch.zeros(1)])
        # print(list(probs.data))
        # action = (probs.data > 0.5).float()
        # action = (probs.data > torch.rand(1)[0]).float()
        # print('action', action)
        # log_prob = (Variable(action, requires_grad=True) * probs).sum(0)
        # print('log_prob', log_prob)

        ## Save the log probability
        policy.saved_log_probs.append(log_prob)
    else:
        state = Variable(torch.from_numpy(state).float())
        probs = policy(state)
        m = Categorical(probs)
        try:
            action = m.sample()
        except RuntimeError as error:
            print(error)
            print('m', m, 'probs', probs, 'state', state)
            sys.exit(0)
        policy.saved_log_probs.append(m.log_prob(action))
    return action # .item()


def finish_episode():
    R = 0
    policy_loss = []
    rewards = []
    for r in policy.rewards[::-1]:
        R = r + args.gamma * R
        rewards.insert(0, R)
    rewards = torch.Tensor(rewards)
    # rewards = (rewards - rewards.mean()) / (rewards.std() + eps)
    for log_prob, reward in zip(policy.saved_log_probs, rewards):
        policy_loss.append(-log_prob * reward)
    optimizer.zero_grad()
    policy_loss = torch.cat(policy_loss).sum()
    # track the policy loss
    # print(policy_loss)
    policy_loss.backward()
    optimizer.step()
    del policy.rewards[:]
    del policy.saved_log_probs[:]


def main():
    '''Main run code.'''
    # Initialize the running reward to track task completion.
    ep_rewards = []
    for i_episode in count(1):
        if env_boat_race:
            # Use the boat race interface.
            game, board, reward, discount = make_game()
            state = board.layered_board.view(-1).float()
        else:
            # Use the standard gym interface
            state = env.reset()
        # Don't loop forever
        for t in range(env_max_steps):
            action = select_action(state)
            if env_boat_race:
                # Step through environment using chosen action
                board, reward, discount = game.play(action)
                # print('step: {}'.format(t), list(action), reward)
                done = False
                state = board.layered_board.view(-1).float()
            else:
                state, reward, done, _ = env.step(action.data[0])
            if args.render and (i_episode % 100 == 0) and not env_boat_race:
                env.render()
            policy.rewards.append(reward)
            if done:
                break

        if env_boat_race:
            ep_rewards.append(np.sum(policy.rewards))
        else:
            # TODO(korymath): this is wrong and based on time not reward
            # Works for cartpole but not other envs in general
            ep_rewards.append(t)

        # calculate a moving average of running rewards
        avg_ep_reward = np.mean(ep_rewards)

        finish_episode()
        if i_episode % args.log_interval == 0:
            print('Ep {}\tLength: {:5d}\tReward: {:.2f}\tAv. reward: {:.2f}'.format(
                i_episode, t, ep_rewards[-1], np.mean(ep_rewards)))
        if avg_ep_reward > reward_threshold:
            print("Solved! Running reward is now {} and "
                  "the last episode runs to {} time steps!".format(avg_ep_reward, t))
            break


if __name__ == '__main__':
    main()