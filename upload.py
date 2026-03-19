# -*- coding: utf-8 -*-
"""
Booru Auto Uploader (GitHub Actions用)
AIBooru (aibooru.online) と Gelbooru (gelbooru.com) に同時投稿
Google Driveからダウンロード → ランダム1ファイルをアップロード
"""
import sys, json, os, random, time

import requests
import gdown

# ============================================================
# 設定
# ============================================================

GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID_BOORU", "")

# AIBooru credentials (HTTP Basic Auth)
AIBOORU_USERNAME = os.environ.get("AIBOORU_USERNAME", "")
AIBOORU_API_KEY = os.environ.get("AIBOORU_API_KEY", "")

# Gelbooru credentials (user_id + api_key)
GELBOORU_USERNAME = os.environ.get("GELBOORU_USERNAME", "")
GELBOORU_API_KEY = os.environ.get("GELBOORU_API_KEY", "")

PATREON_LINK = "https://www.patreon.com/cw/MuscleLove"
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
UPLOADED_LOG = "uploaded_booru.json"

# ============================================================
# Booru用タグ (underscore形式)
# ============================================================

BASE_TAGS = [
    'muscular_female', 'female', 'ai_generated', '1girl', 'solo',
    'muscular', 'abs', 'fitness', 'armpit', 'toned',
    'athletic', 'biceps', 'strong', 'sports_bra',
]

# フォルダ名・ファイル名からコンテンツを推測してタグを生成するマッピング
CONTENT_TAG_MAP = {
    'training': ['exercising', 'gym', 'workout', 'sweat'],
    'workout': ['exercising', 'gym', 'workout', 'sweat'],
    'pullups': ['pull-ups', 'exercise', 'from_below'],
    'posing': ['posing', 'flexing', 'bodybuilder'],
    'flex': ['flexing', 'bodybuilder', 'biceps_flex'],
    'muscle': ['muscular', 'veins', 'toned'],
    'bicep': ['biceps', 'biceps_flex', 'arm_up'],
    'abs': ['abs', 'midriff', 'navel', 'toned_stomach'],
    'leg': ['thighs', 'legs', 'thick_thighs', 'muscular_legs'],
    'back': ['back', 'back_muscles', 'from_behind'],
    'squat': ['squatting', 'legs', 'thick_thighs'],
    'deadlift': ['weightlifting', 'barbell', 'gym'],
    'bench': ['bench_press', 'barbell', 'chest'],
    'bikini': ['bikini', 'swimsuit', 'beach'],
    'nude': ['nude', 'naked', 'nipples'],
    'topless': ['topless', 'nipples', 'breasts'],
    'sweat': ['sweat', 'sweating', 'wet'],
    'tank': ['tank_top', 'sportswear'],
    'sports': ['sportswear', 'sports_bra', 'shorts'],
    'gym': ['gym', 'gym_uniform', 'indoors'],
    'outdoor': ['outdoors', 'sky', 'sunlight'],
    'pool': ['pool', 'swimsuit', 'water', 'wet'],
    'shower': ['shower', 'wet', 'water', 'nude'],
    'dark': ['dark_skin', 'dark-skinned_female'],
    'tan': ['tan', 'tanned'],
    'blonde': ['blonde_hair'],
    'red': ['red_hair'],
    'black_hair': ['black_hair'],
    'short_hair': ['short_hair'],
    'long_hair': ['long_hair'],
    'ponytail': ['ponytail'],
}

# Rating判定用キーワード
EXPLICIT_KEYWORDS = ['nude', 'naked', 'topless', 'nipple', 'pussy', 'nsfw', 'explicit']
QUESTIONABLE_KEYWORDS = ['bikini', 'underwear', 'lingerie', 'bra', 'panties', 'wet', 'shower']


# ============================================================
# アップロード済み管理
# ============================================================

def load_uploaded_log():
    """アップロード済みファイルの記録を読み込む"""
    if not os.path.exists(UPLOADED_LOG):
        return []
    with open(UPLOADED_LOG, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_uploaded_log(log_data):
    """アップロード済みファイルの記録を保存する"""
    with open(UPLOADED_LOG, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


# ============================================================
# Google Driveダウンロード
# ============================================================

def download_media():
    """Google Driveフォルダからメディアファイルをダウンロードする"""
    dl_dir = "media"
    os.makedirs(dl_dir, exist_ok=True)
    url = f"https://drive.google.com/drive/folders/{GDRIVE_FOLDER_ID}"
    print(f"Downloading from Google Drive: {url}")
    try:
        gdown.download_folder(url, output=dl_dir, quiet=False, remaining_ok=True)
    except Exception as e:
        print(f"Download error: {e}")

    files = []
    for root, dirs, filenames in os.walk(dl_dir):
        for fname in filenames:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                size = os.path.getsize(fpath)
                if size <= MAX_FILE_SIZE:
                    files.append(fpath)
                else:
                    print(f"Skip (>100MB): {fname} ({size / 1024 / 1024:.1f}MB)")
    return files


# ============================================================
# タグ・レーティング生成
# ============================================================

def generate_tags(file_path):
    """フォルダ名・ファイル名からコンテンツを推測してBooruタグを生成"""
    tags = list(BASE_TAGS)

    path_lower = file_path.lower().replace('\\', '/').replace('-', ' ').replace('_', ' ')

    matched = set()
    for keyword, keyword_tags in CONTENT_TAG_MAP.items():
        if keyword in path_lower:
            for t in keyword_tags:
                if t not in matched:
                    tags.append(t)
                    matched.add(t)

    # 重複除去しつつ順序保持
    seen = set()
    unique_tags = []
    for t in tags:
        t_lower = t.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            unique_tags.append(t)

    return unique_tags


def determine_rating(file_path):
    """ファイルパスからレーティングを判定する"""
    path_lower = file_path.lower().replace('\\', '/').replace('-', ' ').replace('_', ' ')

    for kw in EXPLICIT_KEYWORDS:
        if kw in path_lower:
            return 'e'  # explicit

    for kw in QUESTIONABLE_KEYWORDS:
        if kw in path_lower:
            return 'q'  # questionable

    return 'q'  # デフォルトはquestionable


# ============================================================
# AIBooru API アップロード
# ============================================================

def upload_to_aibooru(file_path, tag_string, rating, source):
    """AIBooruにファイルをアップロードする"""
    if not AIBOORU_USERNAME or not AIBOORU_API_KEY:
        print("AIBooru: credentials not set, skipping")
        return None

    fname = os.path.basename(file_path)
    size_mb = os.path.getsize(file_path) / 1024 / 1024
    print(f"\n--- AIBooru Upload ---")
    print(f"File: {fname} ({size_mb:.1f}MB)")
    print(f"Tags: {tag_string[:100]}...")
    print(f"Rating: {rating}")

    url = "https://aibooru.online/uploads.json"

    with open(file_path, 'rb') as f:
        files = {
            'upload[file]': (fname, f, 'image/png'),
        }
        data = {
            'upload[tag_string]': tag_string,
            'upload[rating]': rating,
            'upload[source]': source,
        }

        try:
            r = requests.post(
                url,
                data=data,
                files=files,
                auth=(AIBOORU_USERNAME, AIBOORU_API_KEY),
                timeout=300,
            )
        except requests.exceptions.RequestException as e:
            print(f"AIBooru request error: {e}")
            return None

    print(f"AIBooru response: {r.status_code}")
    try:
        result = r.json()
        if r.status_code in (200, 201):
            upload_id = result.get('id', '')
            print(f"AIBooru upload success! ID: {upload_id}")
            return {
                'status': 'success',
                'id': upload_id,
                'url': f"https://aibooru.online/uploads/{upload_id}" if upload_id else '',
            }
        else:
            print(f"AIBooru error: {result}")
            return {'status': 'error', 'detail': str(result)}
    except Exception:
        print(f"AIBooru response body: {r.text[:500]}")
        return {'status': 'error', 'detail': r.text[:200]}


# ============================================================
# Gelbooru API アップロード
# ============================================================

def upload_to_gelbooru(file_path, tag_string, rating, source):
    """Gelbooru にファイルをアップロードする"""
    if not GELBOORU_USERNAME or not GELBOORU_API_KEY:
        print("Gelbooru: credentials not set, skipping")
        return None

    fname = os.path.basename(file_path)
    size_mb = os.path.getsize(file_path) / 1024 / 1024
    print(f"\n--- Gelbooru Upload ---")
    print(f"File: {fname} ({size_mb:.1f}MB)")
    print(f"Tags: {tag_string[:100]}...")
    print(f"Rating: {rating}")

    # Gelbooru uses form-based upload
    url = "https://gelbooru.com/index.php?page=post&s=add"

    with open(file_path, 'rb') as f:
        files = {
            'file': (fname, f, 'image/png'),
        }
        data = {
            'tags': tag_string,
            'rating': rating,
            'source': source,
            'submit': 'Upload',
            'user_id': GELBOORU_USERNAME,
            'api_key': GELBOORU_API_KEY,
        }

        try:
            r = requests.post(
                url,
                data=data,
                files=files,
                timeout=300,
            )
        except requests.exceptions.RequestException as e:
            print(f"Gelbooru request error: {e}")
            return None

    print(f"Gelbooru response: {r.status_code}")

    # Gelbooru returns HTML on success, check for success indicators
    if r.status_code == 200:
        body = r.text[:1000]
        if 'success' in body.lower() or 'image has been uploaded' in body.lower() or r.status_code == 200:
            print("Gelbooru upload appears successful")
            return {
                'status': 'success',
                'detail': 'Upload submitted',
            }
        else:
            print(f"Gelbooru response: {body[:300]}")
            return {'status': 'unknown', 'detail': body[:200]}
    else:
        print(f"Gelbooru error: {r.status_code} {r.text[:300]}")
        return {'status': 'error', 'detail': r.text[:200]}


# ============================================================
# メイン
# ============================================================

def main():
    print("=== Booru Auto Uploader (AIBooru + Gelbooru) ===\n")

    if not GDRIVE_FOLDER_ID:
        print("Error: GDRIVE_FOLDER_ID_BOORU not set")
        return 1

    has_aibooru = AIBOORU_USERNAME and AIBOORU_API_KEY
    has_gelbooru = GELBOORU_USERNAME and GELBOORU_API_KEY

    if not has_aibooru and not has_gelbooru:
        print("Error: No Booru credentials configured")
        print("Set AIBOORU_USERNAME + AIBOORU_API_KEY and/or GELBOORU_USERNAME + GELBOORU_API_KEY")
        return 1

    print(f"AIBooru: {'enabled' if has_aibooru else 'disabled'}")
    print(f"Gelbooru: {'enabled' if has_gelbooru else 'disabled'}")

    # Load upload log
    log_data = load_uploaded_log()

    # Download media from Google Drive
    media_files = download_media()
    if not media_files:
        print("No media files found!")
        return 0

    # Filter out already uploaded
    uploaded_names = [entry['file'] if isinstance(entry, dict) else entry
                      for entry in log_data]
    available = [f for f in media_files if os.path.basename(f) not in uploaded_names]
    if not available:
        print("All files already uploaded!")
        return 0
    print(f"\nAvailable: {len(available)} / Total: {len(media_files)}")

    # Select random file
    selected = random.choice(available)
    fname = os.path.basename(selected)
    print(f"Selected: {fname}")

    # Generate tags and rating
    tags = generate_tags(selected)
    rating = determine_rating(selected)
    tag_string = ' '.join(tags)
    source = PATREON_LINK

    print(f"\nTag string: {tag_string}")
    print(f"Rating: {rating}")
    print(f"Source: {source}")

    # Upload to both sites
    aibooru_result = upload_to_aibooru(selected, tag_string, rating, source)
    gelbooru_result = upload_to_gelbooru(selected, tag_string, rating, source)

    # At least one must succeed
    if not aibooru_result and not gelbooru_result:
        print("\nBoth uploads failed or skipped!")
        return 1

    # Record uploaded file
    entry = {
        'file': fname,
        'uploaded_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'rating': rating,
        'tags': tag_string[:200],
    }
    if aibooru_result:
        entry['aibooru'] = aibooru_result
    if gelbooru_result:
        entry['gelbooru'] = gelbooru_result

    log_data.append(entry)
    save_uploaded_log(log_data)

    remaining = len(available) - 1
    print(f"\nDone! Remaining: {remaining}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
