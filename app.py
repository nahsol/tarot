import time
import random
import hashlib
import html
from datetime import datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI

# =========================================================
# API KEY
# =========================================================
API_KEY = st.secrets.get("OPENAI_API_KEY", None)
if not API_KEY:
    st.error("OPENAI_API_KEY가 설정되지 않았어요.")
    st.stop()

client = OpenAI(api_key=API_KEY)

# =========================================================
# 캐시 / 제한
# =========================================================
MAX_CALLS_PER_MIN = 6
CACHE_TTL_SECONDS = 60 * 30

if "calls" not in st.session_state:
    st.session_state.calls = []
if "cache" not in st.session_state:
    st.session_state.cache = {}
if "last_reading" not in st.session_state:
    st.session_state.last_reading = ""
if "last_cards" not in st.session_state:
    st.session_state.last_cards = []
if "last_theme" not in st.session_state:
    st.session_state.last_theme = ""

# =========================================================
# 배경
# =========================================================
BG_URL = "https://cdn.midjourney.com/c1df322c-ff21-4b92-bc61-3f0ed6243ae8/0_2.png"

# =========================================================
# 타로 카드
# =========================================================
tarot_deck = [
    "0. 바보 (The Fool)", "1. 마법사 (The Magician)", "2. 고위 여사제 (The High Priestess)",
    "3. 여황제 (The Empress)", "4. 황제 (The Emperor)", "5. 교황 (The Hierophant)",
    "6. 연인 (The Lovers)", "7. 전차 (The Chariot)", "8. 힘 (Strength)",
    "9. 은둔자 (The Hermit)", "10. 운명의 수레바퀴 (Wheel of Fortune)", "11. 정의 (Justice)",
    "12. 매달린 사람 (The Hanged Man)", "13. 죽음 (Death)", "14. 절제 (Temperance)",
    "15. 악마 (The Devil)", "16. 탑 (The Tower)", "17. 별 (The Star)",
    "18. 달 (The Moon)", "19. 태양 (The Sun)", "20. 심판 (Judgement)", "21. 세계 (The World)"
]

# =========================================================
# 카드 아이콘
# =========================================================
CARD_ICONS = {
    0:"🌀",1:"🪄",2:"🔮",3:"🌿",4:"🛡️",5:"📜",6:"💞",7:"🏇",
    8:"🦁",9:"🕯️",10:"🎡",11:"⚖️",12:"🪢",13:"🦋",14:"🍶",
    15:"⛓️",16:"⚡",17:"✨",18:"🌙",19:"🌞",20:"📣",21:"🌍"
}
def icon_for_card(name):
    try:
        return CARD_ICONS[int(name.split(".")[0])]
    except:
        return "✦"

# =========================================================
# 카드 톤
# =========================================================
CARD_FLAVOR = {
    "0. 바보":"새 출발의 바람","1. 마법사":"의지와 집중","2. 고위 여사제":"직감과 침묵",
    "3. 여황제":"포근한 성장","4. 황제":"구조와 결단","5. 교황":"의미와 약속",
    "6. 연인":"마음의 선택","7. 전차":"전진의 리듬","8. 힘":"부드러운 용기",
    "9. 은둔자":"내면의 등불","10. 운명의 수레바퀴":"순환의 전환","11. 정의":"균형의 시선",
    "12. 매달린 사람":"관점의 전환","13. 죽음":"끝과 시작","14. 절제":"조화와 치유",
    "15. 악마":"집착의 자각","16. 탑":"진실의 붕괴","17. 별":"희망의 회복",
    "18. 달":"불안의 그림자","19. 태양":"확신의 빛","20. 심판":"각성의 부름","21. 세계":"완성과 귀환"
}

def flavor(card, dir_kr):
    key = card.split(" (")[0]
    base = CARD_FLAVOR.get(key, "신비롭고 다정한 톤")
    return base + (" (내면화된 흐름)" if dir_kr=="역방향" else " (자연스러운 확장)")

# =========================================================
# 질문 분류
# =========================================================
def classify_question(q):
    q = q.lower()
    if any(x in q for x in ["불안","걱정","무서","초조"]):
        return {"theme":"불안","voice":"더 느리고 부드럽게"}
    if any(x in q for x in ["사랑","연애","관계","이별"]):
        return {"theme":"관계","voice":"따뜻하지만 단정하지 않게"}
    if any(x in q for x in ["일","회사","진로","퇴사"]):
        return {"theme":"일/진로","voice":"현실을 품되 희망적으로"}
    return {"theme":"삶의 흐름","voice":"신비 50 / 다정 50"}

# =========================================================
# 오프닝 스타일
# =========================================================
OPENING_STYLES = [
    "문이 열리는 순간처럼 시작해라.",
    "숨을 고르는 장면에서 시작해라.",
    "길 위에 서 있는 장면으로 시작해라.",
    "바람이나 물결의 움직임으로 시작해라.",
    "거울에 비친 시선으로 시작해라."
]

# =========================================================
# ⭐ 5장 흐름 힌트 (추가된 핵심)
# =========================================================
FIVE_CARD_FLOW_HINT = """
이 리딩은 다섯 장의 흐름으로 이어진다.
첫 장은 이 상황이 시작된 뿌리와 원인을 비추고,
두 번째 장은 지금 서 있는 현재의 자리를 말한다.
세 번째 장은 보이지 않게 발목을 잡는 방해와 그림자를 드러낸다.
네 번째 장은 이 흐름을 풀기 위한 열쇠와 단서를 건넨다.
마지막 장은 가까운 미래의 방향과 흐름을 조용히 가리킨다.

각 문단은 서로 이어져 하나의 이야기처럼 흘러가야 한다.
"""

# =========================================================
# 프롬프트 (규칙 유지)
# =========================================================
SYSTEM_PROMPT = """
너는 ‘미스틱 타로 마스터’다.
말투는 다정하고 신비로우며, 상대를 가르치지 않고 곁에 머문다.

- 정/역방향 반영
- 단정 금지
- 명령형 금지
- 번호/목록 금지
- 자연스러운 문단 구성
- 마지막은 힘이 나는 축복
"""

# =========================================================
# 모델 호출
# =========================================================
def call_model(question, cards):
    meta = classify_question(question)
    opening = random.choice(OPENING_STYLES)

    flow_hint = FIVE_CARD_FLOW_HINT if len(cards)==5 else ""

    card_lines = []
    for c in cards:
        card_lines.append(
            f"{c['pos']} 카드: {c['name']} ({c['dir_kr']}) → {flavor(c['name'], c['dir_kr'])}"
        )

    prompt = f"""
[질문 테마]
{meta['theme']} / 목소리: {meta['voice']}

[오프닝 힌트]
{opening}

[흐름 힌트]
{flow_hint}

[질문]
{question}

[카드 힌트]
{chr(10).join(card_lines)}
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":prompt}
        ],
        temperature=0.95
    )

    return res.choices[0].message.content.strip()

# =========================================================
# UI
# =========================================================
st.set_page_config(page_title="미스틱 AI 타로관", page_icon="🔮", layout="centered")

st.markdown(f"""
<style>
.stApp {{
  background-image:url("{BG_URL}");
  background-size:cover;
}}
.title {{
  font-family:'Cinzel',serif;
  font-size:clamp(2.2rem,6vw,3rem);
  text-align:center;
  color:#f0e68c;
}}
.card {{
  border:2px solid #d4af37;
  border-radius:16px;
  padding:14px;
  text-align:center;
  background:linear-gradient(135deg,#2c003e,#000);
}}
.panel {{
  margin-top:18px;
  padding:20px;
  background:rgba(20,0,40,.85);
  border-radius:18px;
  line-height:1.9;
}}
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='title'>🔮 미스틱 AI 타로관</div>", unsafe_allow_html=True)

mode = st.radio("모드", ["3장","5장"], horizontal=True)
question = st.text_input("질문")

if st.button("카드 뽑기"):
    n = 3 if mode=="3장" else 5
    positions = ["과거","현재","미래"] if n==3 else ["원인","현재","방해","열쇠","흐름"]
    names = random.sample(tarot_deck, n)

    cards=[]
    for name,pos in zip(names,positions):
        rev=random.choice([True,False])
        cards.append({
            "name":name,
            "pos":pos,
            "dir_kr":"역방향" if rev else "정방향"
        })

    reading = call_model(question, cards)
    st.session_state.last_cards = cards
    st.session_state.last_reading = reading

# =========================================================
# 결과
# =========================================================
if st.session_state.last_cards:
    cols = st.columns(len(st.session_state.last_cards))
    for i,c in enumerate(st.session_state.last_cards):
        with cols[i]:
            st.markdown(f"""
            <div class="card">
              <div>{icon_for_card(c['name'])}</div>
              <div>{c['pos']}</div>
              <div>{c['name']}</div>
              <div>{c['dir_kr']}</div>
            </div>
            """, unsafe_allow_html=True)

    html_reading = "<p>" + "</p><p>".join(
        html.escape(st.session_state.last_reading).split("\n\n")
    ) + "</p>"

    st.markdown(f"<div class='panel'>{html_reading}</div>", unsafe_allow_html=True)
