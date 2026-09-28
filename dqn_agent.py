import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque
from ev_gym_env import EVChargingEnv  
import sys

# Force UTF-8 output on Windows to prevent UnicodeEncodeError for emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')
class DQN(nn.Module):
    def __init__(self, input_size, output_size):
        super(DQN, self).__init__()
        self.network = nn.Sequential(
            nn.Linear(input_size, 64),  
            nn.ReLU(),                  
            nn.Linear(64, 64),          
            nn.ReLU(),
            nn.Linear(64, output_size)  
        )

    def forward(self, x):
        return self.network(x)
class DQNAgent:
    def __init__(self, state_size, action_size):
        self.state_size = state_size
        self.action_size = action_size
        
        self.gamma = 0.95 
        self.epsilon = 1.0  
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.9995
        self.learning_rate = 0.001
        self.batch_size = 32
        
        self.memory = deque(maxlen=2000)
        
        self.device = torch.device("cpu") 
        self.model = DQN(state_size, action_size).to(self.device)
        
        # Initialize target network
        self.target_model = DQN(state_size, action_size).to(self.device)
        self.target_model.load_state_dict(self.model.state_dict())
        self.target_model.eval() # Target network is used for evaluation/inference only
        
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        self.criterion = nn.MSELoss()
        
    def update_target_network(self):
        """Synchronize the target network with the main policy network"""
        self.target_model.load_state_dict(self.model.state_dict())

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state, valid_mask=None):
        if valid_mask is None:
            valid_mask = np.ones(self.action_size, dtype=bool)
            
        if np.random.rand() <= self.epsilon:
            valid_indices = np.where(valid_mask)[0]
            return random.choice(valid_indices)
        
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.model(state_tensor).squeeze(0)
            q_values[~torch.BoolTensor(valid_mask).to(self.device)] = float('-inf')
            return torch.argmax(q_values).item()

    def act_greedy(self, state, valid_mask=None):
        if valid_mask is None:
            valid_mask = np.ones(self.action_size, dtype=bool)
            
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.model(state_tensor).squeeze(0)
            q_values[~torch.BoolTensor(valid_mask).to(self.device)] = float('-inf')
            return torch.argmax(q_values).item()

    def replay(self, batch_size=32):
        if len(self.memory) < batch_size:
            return 0.0

        minibatch = random.sample(self.memory, batch_size)
        
        states = torch.FloatTensor(np.array([i[0] for i in minibatch])).to(self.device)
        actions = torch.LongTensor(np.array([i[1] for i in minibatch])).unsqueeze(1).to(self.device)
        rewards = torch.FloatTensor(np.array([i[2] for i in minibatch])).to(self.device)
        next_states = torch.FloatTensor(np.array([i[3] for i in minibatch])).to(self.device)
        dones = torch.FloatTensor(np.array([i[4] for i in minibatch])).to(self.device)

        current_q = self.model(states).gather(1, actions).squeeze(1)
        
        # Use target network to compute next_q targets (Double DQN concept or just standard DQN target)
        with torch.no_grad():
            next_q = self.target_model(next_states).max(1)[0]
            
        target_q = rewards + (self.gamma * next_q * (1 - dones))
        
        loss = self.criterion(current_q, target_q)
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
            
        return loss.item()

if __name__ == "__main__":
    env = EVChargingEnv()
    
    state_size = env.observation_space.shape[0]
    action_size = env.action_space.n
    agent = DQNAgent(state_size, action_size)
    
    EPISODES = 100
    batch_size = 32
    
    print("🚀 Starting Training for 100 Episodes...", flush=True)
    for e in range(EPISODES):
        state, _ = env.reset()
        terminated = False
        truncated = False
        total_reward = 0
        steps = 0
        total_loss = 0
        
        while not terminated and not truncated:
            valid_mask = env.valid_actions_mask()
            action = agent.act(state, valid_mask)
            
            next_state, reward, terminated, truncated, _ = env.step(action)
            
            agent.remember(state, action, reward, next_state, terminated or truncated)
            
            state = next_state
            total_reward += reward
            steps += 1
            
            if len(agent.memory) > batch_size:
                loss = agent.replay(batch_size)
                total_loss += loss

        agent.update_target_network()

        if e % 10 == 0:
            avg_loss = total_loss / max(1, steps)
            print(f"Episode {e+1}/{EPISODES} | Steps: {steps} | Score: {total_reward:.2f} | Loss: {avg_loss:.4f} | Epsilon: {agent.epsilon:.2f}", flush=True)
            torch.save(agent.model.state_dict(), "ev_dqn_model_v5.pth")
            
    torch.save(agent.model.state_dict(), "ev_dqn_model_v5.pth")
    print("\n✅ Training complete! Model saved to ev_dqn_model_v5.pth")