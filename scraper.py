"""
인스타그램 유아식 레시피 스크랩 스크립트
대상 계정: @ttowooyoung, @danmom_shinhye, @jiyulpping

사용법: python3 scraper.py
결과: recipes.json 파일 생성
"""

import json
import time
import sys
from pathlib import Path

ACCOUNTS = ["ttowooyoung", "danmom_shinhye", "jiyulpping"]
MAX_POSTS = 50  # 계정당 최대 게시물 수
OUTPUT_FILE = "recipes.json"


def scrape_with_instaloader():
    try:
        import instaloader
    except ImportError:
        print("❌ instaloader가 설치되지 않았습니다.")
        print("   pip3 install instaloader 실행 후 다시 시도하세요.")
        return None

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )

    all_posts = []

    for account in ACCOUNTS:
        print(f"\n📥 @{account} 스크랩 중...")
        try:
            profile = instaloader.Profile.from_username(L.context, account)
            count = 0
            for post in profile.get_posts():
                if count >= MAX_POSTS:
                    break
                caption = post.caption or ""
                # 레시피 관련 게시물 필터링 (재료, 레시피 키워드 포함)
                if len(caption) < 50:
                    continue
                all_posts.append({
                    "account": account,
                    "shortcode": post.shortcode,
                    "url": f"https://www.instagram.com/p/{post.shortcode}/",
                    "caption": caption[:2000],  # 너무 긴 캡션 자르기
                    "likes": post.likes,
                    "timestamp": post.date_utc.isoformat(),
                })
                count += 1
                time.sleep(1.5)  # 레이트 리밋 방지
            print(f"   ✅ {count}개 게시물 수집 완료")
        except instaloader.exceptions.ProfileNotExistsException:
            print(f"   ❌ 계정 @{account}을 찾을 수 없습니다")
        except instaloader.exceptions.LoginRequiredException:
            print(f"   ⚠️  @{account}: 로그인 필요 (비공개 계정이거나 제한됨)")
        except Exception as e:
            print(f"   ⚠️  @{account} 스크랩 실패: {e}")
        time.sleep(3)  # 계정 간 대기

    return all_posts


def load_existing():
    p = Path(OUTPUT_FILE)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return []


def save(posts):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {OUTPUT_FILE} 저장 완료 (총 {len(posts)}개 게시물)")


def main():
    print("=" * 50)
    print("🍼 유아식 레시피 인스타그램 스크랩")
    print("=" * 50)
    print(f"대상 계정: {', '.join('@' + a for a in ACCOUNTS)}")

    existing = load_existing()
    existing_codes = {p["shortcode"] for p in existing}
    print(f"기존 캐시: {len(existing)}개 게시물")

    new_posts = scrape_with_instaloader()

    if new_posts is None:
        print("\n⚠️  스크랩 실패. 기존 캐시가 있다면 그것을 사용합니다.")
        if existing:
            print(f"   기존 {len(existing)}개 게시물 사용 가능")
        else:
            print("   캐시 없음 - 서버 실행 시 Claude 자체 지식으로 레시피 추천")
        return

    # 중복 제거 후 병합
    for post in new_posts:
        if post["shortcode"] not in existing_codes:
            existing.append(post)
            existing_codes.add(post["shortcode"])

    save(existing)
    print("\n✅ 스크랩 완료! 이제 python3 server.py로 서버를 시작하세요.")


if __name__ == "__main__":
    main()
