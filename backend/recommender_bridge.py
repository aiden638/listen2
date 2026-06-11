"""backend에서 루트의 MusicRecommender를 쓰기 위한 얇은 연결 계층.

- 루트 폴더(backend의 부모)를 sys.path에 추가해 recommender 모듈을 import한다.
- 무거운 모델(torch/kmeans)은 첫 호출 때 한 번만 로딩하는 싱글톤으로 관리한다.
  → 서버 부팅이 느려지지 않고, 추천 기능을 안 쓰면 torch도 로드되지 않는다.
  → 싱글톤이라 recommender의 '최근 재생곡 페널티' 기록이 요청 간에 유지되어 같은 곡 반복을 막는다.

기존 recommender.py / main.py / train_model.py는 전혀 수정하지 않는다.
"""
import os
import sys
import warnings

# recommender가 scaler.transform에 (컬럼명 없는) numpy 배열을 넘겨서 나오는 무해한 경고.
# 결과엔 영향 없고 터미널만 도배하므로 이 경고만 끈다(추천 코어는 수정하지 않음).
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names",
    category=UserWarning,
)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)

_recommender = None


def get_recommender():
    """MusicRecommender 싱글톤을 반환한다. 최초 호출 시에만 모델을 로딩한다."""
    global _recommender
    if _recommender is None:
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)
        # 무거운 의존성(torch 등)은 이 시점에 처음 import된다.
        from recommender import MusicRecommender
        _recommender = MusicRecommender()
    return _recommender
