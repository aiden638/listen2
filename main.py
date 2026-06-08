from recommender import MusicRecommender

def main():
    print("Loading Music Recommender System...")
    try:
        recommender = MusicRecommender()
    except Exception as e:
        print(f"Error loading models or data: {e}")
        print("Make sure to run 'train_model.py' first.")
        return

    chat_input = ["긴장", "환장", "전율", "돌진", "카타르시스"]
    print(f"\n[채팅 입력 키워드 추출]: {chat_input}")
    
    print("\n추천 노래 검색 중...")
    recommended_song = recommender.recommend(chat_input)
    
    print("\n" + "="*50)
    print("🎯 최종 추천 1곡")
    print("="*50)
    print(f"🎵 제목: {recommended_song['track_name']}")
    print(f"🎤 아티스트: {recommended_song['artist_name']}")
    if 'album_name' in recommended_song:
        print(f"💿 앨범: {recommended_song['album_name']}")
    print(f"🔢 소속 클러스터: {recommended_song['cluster_id']}")
    print(f"📉 페널티 후 최종 점수(거리): {recommended_song['final_score']:.4f}")
    print("="*50)

if __name__ == "__main__":
    main()
