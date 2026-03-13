import os
import json
import asyncio
import subprocess
import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

app = FastAPI()

api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise RuntimeError(
        "\n\n❌ ANTHROPIC_API_KEY가 설정되지 않았습니다.\n"
        "프로젝트 폴더에 .env 파일을 만들고 아래 내용을 추가하세요:\n\n"
        "  ANTHROPIC_API_KEY=sk-ant-...\n"
    )

client = anthropic.Anthropic(api_key=api_key)

INSTAGRAM_ACCOUNTS = ["ttowooyoung", "danmom_shinhye", "jiyulpping"]
RECIPES_FILE = Path("recipes.json")

BASE_SYSTEM_PROMPT = """당신은 유아식 전문 영양사입니다. 부모가 냉장고에 있는 재료를 알려주면,
그 재료로 만들 수 있는 유아식 레시피를 추천해 주세요.

{instagram_context}

레시피 추천 시 반드시 다음 형식을 사용하세요:

---RECIPE_START---
**레시피 이름**: (이름 + 이모지)
**출처**: @계정명 (인스타그램 레시피 기반이면 명시, 아니면 "AI 추천")
**월령**: (예: 6개월 이상)
**재료**: (목록)
**조리법**: (단계별)
**영양 포인트**: (1-2가지)
**주의사항**: (알레르기, 주의사항)
---RECIPE_END---

위 형식으로 2-3개 추천해 주세요.
인스타그램 레시피 데이터가 있다면 우선적으로 활용하고,
인스타 레시피 출처를 명시할 때는 반드시 @계정명을 포함하세요."""

FALLBACK_CONTEXT = """
[참고 인스타그램 계정: @ttowooyoung, @danmom_shinhye, @jiyulpping]
인스타그램 데이터가 현재 없습니다. 해당 계정 스타일(한국식 유아식, 자연식 위주)에 맞게 레시피를 추천하되,
출처는 "AI 추천"으로 표기하세요."""


def load_recipes() -> list:
    if RECIPES_FILE.exists():
        try:
            with open(RECIPES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def build_instagram_context(recipes: list) -> str:
    if not recipes:
        return FALLBACK_CONTEXT

    lines = [
        f"\n아래는 인스타그램 {', '.join('@' + a for a in INSTAGRAM_ACCOUNTS)} 계정의 실제 유아식 레시피 게시물입니다:",
        "사용자의 재료와 가장 잘 맞는 레시피를 이 목록에서 우선 찾아 추천해 주세요.\n"
    ]
    for i, post in enumerate(recipes, 1):
        lines.append(f"[게시물 {i}] @{post['account']} ({post.get('url', '')})")
        lines.append(post["caption"][:800])
        lines.append("---")
    return "\n".join(lines)


class RecipeRequest(BaseModel):
    ingredients: List[str]
    baby_age: str = "6개월 이상"


@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/status")
async def get_status():
    recipes = load_recipes()
    counts = {}
    for p in recipes:
        a = p.get("account", "unknown")
        counts[a] = counts.get(a, 0) + 1
    return JSONResponse({
        "total": len(recipes),
        "by_account": counts,
        "has_data": len(recipes) > 0,
    })


@app.post("/api/scrape")
async def trigger_scrape():
    """스크랩 실행 트리거 (백그라운드)"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "scraper.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode == 0:
            recipes = load_recipes()
            return JSONResponse({"success": True, "total": len(recipes), "message": stdout.decode()})
        else:
            return JSONResponse({"success": False, "error": stderr.decode()}, status_code=500)
    except asyncio.TimeoutError:
        return JSONResponse({"success": False, "error": "스크랩 시간 초과 (5분)"}, status_code=504)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/recipes/stream")
async def get_recipes_stream(request: RecipeRequest):
    recipes = load_recipes()
    instagram_context = build_instagram_context(recipes)
    system_prompt = BASE_SYSTEM_PROMPT.format(instagram_context=instagram_context)

    ingredients_text = ", ".join(request.ingredients)
    user_message = f"""아이 나이: {request.baby_age}
냉장고 재료: {ingredients_text}

위 재료들로 만들 수 있는 유아식 레시피를 추천해 주세요.
인스타그램 레시피 데이터를 최대한 활용해서 실제 검증된 레시피를 알려주세요."""

    def generate():
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=3000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
