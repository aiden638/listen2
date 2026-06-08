import json
import numpy as np
import pandas as pd
import torch
import joblib
from scipy.spatial.distance import cdist
import os
from train_model import AudioAutoEncoder, FEATURES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)

# Sensible defaults for features if missing
DEFAULT_FEATURES = {
    'danceability': 0.5,
    'energy': 0.5,
    'speechiness': 0.05,
    'acousticness': 0.5,
    'instrumentalness': 0.0,
    'liveness': 0.2,
    'valence': 0.5,
    'tempo': 120.0,
    'loudness': -6.0
}

class MusicRecommender:
    def __init__(self, model_dir=os.path.join(BASE_DIR, "models"), data_path=os.path.join(BASE_DIR, "final_dataset.csv"), word_json=os.path.join(BASE_DIR, "word_audio_profiles_2000_flat.json")):
        # Load scaler
        self.scaler = joblib.load(os.path.join(model_dir, "scaler.pkl"))
        
        # Load AutoEncoder
        self.autoencoder = AudioAutoEncoder(input_dim=len(FEATURES), latent_dim=4)
        self.autoencoder.load_state_dict(torch.load(os.path.join(model_dir, "autoencoder.pth")))
        self.autoencoder.eval()
        
        # Load KMeans
        self.kmeans = joblib.load(os.path.join(model_dir, "kmeans.pkl"))
        
        # Load song data (with latent vectors)
        self.df_songs = pd.read_csv(os.path.join(model_dir, "processed_songs.csv"))
        self.latent_cols = [col for col in self.df_songs.columns if col.startswith('latent_')]
        self.song_latents = self.df_songs[self.latent_cols].values
        
        # Load word dictionary
        with open(word_json, "r", encoding="utf-8") as f:
            self.word_dict = json.load(f)
            
        # History for penalties
        self.played_track_ids = []
        self.played_album_names = []
        self.played_artists = []
        self.played_clusters = []
        
    def get_word_latent(self, word):
        if word not in self.word_dict:
            return None
        target = self.word_dict[word]['target']
        # Extract features in the correct order, using sensible defaults
        features_array = np.array([[target.get(f, DEFAULT_FEATURES[f]) for f in FEATURES]])
        # Scale
        scaled_features = self.scaler.transform(features_array)
        # Encode
        tensor_features = torch.tensor(scaled_features, dtype=torch.float32)
        with torch.no_grad():
            latent = self.autoencoder.encoder(tensor_features).numpy()[0]
        return latent

    def recommend(self, words):
        valid_latents = []
        for w in words:
            latent = self.get_word_latent(w)
            if latent is not None:
                valid_latents.append(latent)
                
        if not valid_latents:
            print("No valid words found in the dictionary.")
            # Fallback to random popular song
            return self.df_songs.sample(1).iloc[0]
            
        # 1. Weighted Average of latent vectors
        # Give higher weight to the first words (e.g., 1.0, 0.8, 0.6...)
        word_weights = np.linspace(1.0, 0.4, len(valid_latents))
        mood_vector = np.average(valid_latents, axis=0, weights=word_weights).reshape(1, -1)
        
        # 2. Calculate distances to all songs
        distances = cdist(mood_vector, self.song_latents, metric='euclidean')[0]
        
        # 3. Get Top 50 candidates
        top_50_idx = np.argsort(distances)[:50]
        candidates = self.df_songs.iloc[top_50_idx].copy()
        candidates['base_distance'] = distances[top_50_idx]
        candidates['penalty'] = 0.0
        
        # 4. Apply Deduplication Penalties
        # Penalty: Same Track (Prohibit)
        if 'track_id' in candidates.columns:
            for track in self.played_track_ids[-20:]: # Check last 20 tracks
                candidates.loc[candidates['track_id'] == track, 'penalty'] += 999.0
                
        # Penalty: Same Album
        if 'album_name' in candidates.columns:
            for album in self.played_album_names[-10:]:
                candidates.loc[candidates['album_name'] == album, 'penalty'] += 1.0
                
        # Penalty: Same Artist
        for artist in self.played_artists[-10:]:
            candidates.loc[candidates['artist_name'] == artist, 'penalty'] += 1.5
            
        # Penalty: Same Cluster
        for cluster in self.played_clusters[-5:]:
            candidates.loc[candidates['cluster_id'] == cluster, 'penalty'] += 0.5
            
        # Final Score = Base Distance + Penalty
        candidates['final_score'] = candidates['base_distance'] + candidates['penalty']
        
        # 5. Probabilistic Selection from Top 10
        # Sort by final score (lower is better)
        top_10 = candidates.sort_values(by='final_score').head(10)
        
        # Convert score to probability: lower score -> higher probability
        # Using inverse of score, adding small epsilon to avoid division by zero
        scores = top_10['final_score'].values
        inv_scores = 1.0 / (scores + 1e-3)
        probabilities = inv_scores / inv_scores.sum()
        
        # Choose 1 song based on probabilities
        chosen_idx = np.random.choice(len(top_10), p=probabilities)
        best_song = top_10.iloc[chosen_idx]
        
        # Update history
        if 'track_id' in best_song:
            self.played_track_ids.append(best_song['track_id'])
        if 'album_name' in best_song:
            self.played_album_names.append(best_song['album_name'])
        self.played_artists.append(best_song['artist_name'])
        self.played_clusters.append(best_song['cluster_id'])
        
        return best_song
