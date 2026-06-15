import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import joblib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)

# Define the features to use
FEATURES = ['danceability', 'energy', 'speechiness', 'acousticness', 
            'instrumentalness', 'liveness', 'valence', 'tempo', 'loudness']

# Define the AutoEncoder Model
# 구조는 배포된 models/autoencoder.pth 와 정확히 일치해야 한다(레이어 인덱스/크기).
# encoder: 9→64→32→16→latent, decoder: latent→16→32→64→9 (Linear 사이 ReLU, 일부 Dropout).
# 검증: 이 인코더로 데이터셋을 인코딩하면 models/processed_songs.csv 의 latent_* 와 일치함.
class AudioAutoEncoder(nn.Module):
    def __init__(self, input_dim=9, latent_dim=4):
        super(AudioAutoEncoder, self).__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 64),  # 0
            nn.ReLU(),                 # 1
            nn.Dropout(0.2),           # 2
            nn.Linear(64, 32),         # 3
            nn.ReLU(),                 # 4
            nn.Dropout(0.2),           # 5
            nn.Linear(32, 16),         # 6
            nn.ReLU(),                 # 7
            nn.Linear(16, latent_dim)  # 8
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 16), # 0
            nn.ReLU(),                 # 1
            nn.Linear(16, 32),         # 2
            nn.ReLU(),                 # 3
            nn.Dropout(0.2),           # 4
            nn.Linear(32, 64),         # 5
            nn.ReLU(),                 # 6
            nn.Dropout(0.2),           # 7
            nn.Linear(64, input_dim)   # 8
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent

def main():
    print("Loading data...")
    # Load dataset
    df = pd.read_csv(os.path.join(BASE_DIR, "final_dataset.csv"))
    
    # Drop rows with NaN in required features
    df = df.dropna(subset=FEATURES).copy()
    
    # Scale numerical features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df[FEATURES])
    
    # Convert to PyTorch tensors
    X_tensor = torch.tensor(X_scaled, dtype=torch.float32)
    
    # Initialize model, loss, and optimizer
    model = AudioAutoEncoder(input_dim=len(FEATURES), latent_dim=4)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    
    # Train AutoEncoder
    print("Training AutoEncoder...")
    epochs = 50
    batch_size = 256
    dataset = torch.utils.data.TensorDataset(X_tensor)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for batch in dataloader:
            batch_x = batch[0]
            optimizer.zero_grad()
            reconstructed, _ = model(batch_x)
            loss = criterion(reconstructed, batch_x)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        if (epoch+1) % 10 == 0:
            print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(dataloader):.4f}")
            
    # Generate latent vectors for all songs
    print("Generating latent vectors...")
    model.eval()
    with torch.no_grad():
        _, latent_vectors = model(X_tensor)
        latent_np = latent_vectors.numpy()
        
    # KMeans Clustering
    print("Training KMeans clustering...")
    num_clusters = 10
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    cluster_ids = kmeans.fit_predict(latent_np)
    
    # Save the latent vectors and cluster IDs to the dataframe
    for i in range(latent_np.shape[1]):
        df[f'latent_{i}'] = latent_np[:, i]
    df['cluster_id'] = cluster_ids
    
    # Save models and processed data
    print("Saving models and data...")
    model_dir = os.path.join(BASE_DIR, 'models')
    os.makedirs(model_dir, exist_ok=True)
    
    # Save PyTorch model state
    torch.save(model.state_dict(), os.path.join(model_dir, "autoencoder.pth"))
    
    # Save Scaler and KMeans
    joblib.dump(scaler, os.path.join(model_dir, "scaler.pkl"))
    joblib.dump(kmeans, os.path.join(model_dir, "kmeans.pkl"))
    
    # Save processed dataframe
    df.to_csv(os.path.join(model_dir, "processed_songs.csv"), index=False)
    print("Training complete! Files saved in 'models' folder.")

if __name__ == "__main__":
    main()
