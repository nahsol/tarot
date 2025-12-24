import time
import random
import hashlib
from datetime import datetime, timedelta

import streamlit as st
from openai import OpenAI

# =========================================================
# API KEY (Streamlit secrets 사용)
# =========================================================
# Streamlit Cloud에서: Settings > Secrets 에 OPENAI_API_KEY 넣기
API_KEY = st.secrets.get("OPENAI_API_KEY", None)
if not API_KEY:
    st.error("OPENAI_API_KEY가 설정되지 않았어요. Streamlit Secrets에 OPENAI_API_KEY를 넣어주세요.")
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
    st.session_state.cache = {}  # key -> (expires_at, reading)

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
# 카드별 "온도/상징/말투" (1번 기능)
# =========================================================
CARD_FLAVOR = {
    "0. 바보": "새 출발의 바람, 가벼운 발걸음, 실수도 축복으로 바꾸는 톤",
    "1. 마법사": "의지와 집중, 손끝의 불꽃, ‘할 수 있다’는 조용한 확신의 톤",
    "2. 고위 여사제": "달빛과 직감, 말보다 침묵, 비밀스런 안내자의 톤",
    "3. 여황제": "포근함과 성장, 향기와 풍요, 안아주는 엄마 같은 톤",
    "4. 황제": "구조와 경계, 책임과 결단, 단단한 바위 같은 톤(차갑지 않게)",
    "5. 교황": "의미와 배움, 전통과 약속, ‘너는 혼자가 아니다’ 같은 톤",
    "6. 연인": "마음의 선택, 끌림과 약속, 두 사람 사이의 숨결 같은 톤",
    "7. 전차": "전진의 리듬, 의지와 승부, 북소리처럼 끌고 가는 톤",
    "8. 힘": "부드러운 용기, 야수의 숨을 달래는 톤, 다정하지만 강한 톤",
    "9. 은둔자": "등불 하나, 느린 걸음, 나에게 돌아오는 톤",
    "10. 운명의 수레바퀴": "순환과 반전, 흐름의 전환, ‘때가 바뀐다’는 톤",
    "11. 정의": "균형과 정직, 가벼운 심판이 아닌 공정한 시선의 톤",
    "12. 매달린 사람": "멈춤과 관점 전환, 내려놓음, 기다림의 톤",
    "13. 죽음": "끝과 시작, 낡은 껍질의 탈피, 무섭지 않게 따뜻한 톤",
    "14. 절제": "혼합과 치유, 온도 조절, 숨 고르는 톤",
    "15. 악마": "집착과 유혹, 사슬의 자각, 비난 없이 다정히 풀어주는 톤",
    "16. 탑": "갑작스런 깨짐, 진실의 번개, ‘무너져도 너는 남는다’ 톤",
    "17. 별": "희망과 회복, 밤하늘의 약속, 반짝임이 스미는 톤",
    "18. 달": "불안과 환영, 안개와 꿈, ‘두려움도 길의 일부’ 톤",
    "19. 태양": "따뜻한 확신, 밝은 생기, 애정 어린 축복의 톤",
    "20. 심판": "각성의 부름, 다시 시작, ‘이제 너의 이름을 불러’ 톤",
    "21. 세계": "완성과 귀환, 한 바퀴의 끝, ‘너는 해냈다’ 톤",
}

def get_card_key(card_name: str) -> str:
    return card_name.split(" (")[0].strip()

def card_flavor_text(card_name: str, direction_kr: str) -> str:
    key = get_card_key(card_name)
    base = CARD_FLAVOR.get(key, "신비롭고 다정한 톤")
    if direction_kr == "역방향":
        return base + " + 역방향: 내면의 막힘/지연/오해를 부드럽게 풀어주는 결"
    return base + " + 정방향: 흐름이 열리는 쪽으로 자연스럽게 확장"

# =========================================================
# 질문 톤 분류 (2번 기능)
# =========================================================
def classify_question(q: str):
    s = q.lower()

    anxiety_kw = ["불안", "무서", "두려", "걱정", "초조", "공황", "우울", "지겹", "힘들", "괴로", "멘탈", "불면", "스트레스"]
    love_kw = ["연애", "사랑", "썸", "남친", "여친", "짝사랑", "헤어", "이별", "관계", "호감", "마음", "결혼"]
    work_kw = ["직장", "회사", "퇴사", "이직", "승진", "면접", "상사", "동료", "프로젝트", "진로", "커리어", "시험", "취업"]
    self_kw = ["자존감", "자신감", "내가", "나는 왜", "무가치", "못하겠", "열등", "비교", "자책"]

    def hit(lst):
        return sum(1 for w in lst if w in s)

    a, l, w, se = hit(anxiety_kw), hit(love_kw), hit(work_kw), hit(self_kw)

    if a >= max(l, w, se) and a > 0:
        return {
            "theme": "불안/흔들림",
            "voice": "더 부드럽게, 더 천천히, 안심시키며 동행하는 목소리",
            "caution": "불안을 키우지 말고 낮춰라. ‘괜찮아’보다 ‘곁에 있어’ 쪽으로."
        }
    if l >= max(a, w, se) and l > 0:
        return {
            "theme": "연애/관계",
            "voice": "따뜻하지만 달콤하게만 가지 말고, 마음의 선택을 다정히 비춰주는 목소리",
            "caution": "상대 단정 금지. 관계의 ‘흐름’과 ‘대화의 숨결’을 말해라."
        }
    if w >= max(a, l, se) and w > 0:
        return {
            "theme": "일/진로",
            "voice": "현실감은 품되 리포트처럼 말하지 말고, 용기를 북돋는 목소리",
            "caution": "지시형 조언 금지. ‘가능성’과 ‘기운’ 중심."
        }
    if se > 0:
        return {
            "theme": "자존감/자기이해",
            "voice": "다정함을 10% 더 올려서, 자책을 녹이는 목소리",
            "caution": "비난 금지. ‘너는 이미 충분하다’ 결로 마무리."
        }
    return {
        "theme": "일반/삶의 흐름",
        "voice": "신비 50, 다정 50의 기본 톤",
        "caution": "짧게 끊지 말고 호흡 길게."
    }

# =========================================================
# 오프닝 시작 스타일 (반복 방지용 랜덤)
# =========================================================
OPENING_STYLES = [
    "오프닝은 ‘문을 여는’ 느낌으로 시작해라. (예: 문턱, 문장, 열쇠, 문이 열리는 소리)",
    "오프닝은 ‘숨’으로 시작해라. (예: 숨결, 한숨, 고요, 가슴의 파도)",
    "오프닝은 ‘길’로 시작해라. (예: 갈림길, 발자국, 지도 없는 길)",
    "오프닝은 ‘별/하늘’로 시작해라. 단, ‘달빛이 내리쬔다’ 금지.",
    "오프닝은 ‘바람’으로 시작해라. (예: 바람이 스친다, 바람결이 말한다)",
    "오프닝은 ‘물’로 시작해라. (예: 파도, 물결, 잔잔한 수면, 빗방울)",
    "오프닝은 ‘불꽃/촛불’로 시작해라. (예: 작은 불, 심지, 따뜻한 빛)",
    "오프닝은 ‘안개’로 시작해라. 단, 밤/달/별 언급 없이도 성립하게.",
    "오프닝은 ‘거울’로 시작해라. (예: 비추다, 반사, 내 얼굴의 다른 표정)",
    "오프닝은 ‘종소리/울림’으로 시작해라. (예: 울림, 진동, 맥박)",
    "오프닝은 ‘손’으로 시작해라. (예: 손끝, 쥔 것, 놓는 것)",
    "오프닝은 ‘지금-여기’로 시작해라. 단, 시간대(밤) 단정 금지."
]

# =========================================================
# 🔮 프롬프트 (줄바꿈 OK / 문단 OK / 번호·불릿 금지)  ← 너 코드 그대로
# =========================================================
SYSTEM_PROMPT = """
너는 ‘미스틱 타로 마스터’다.
말투는 다정하고 신비로우며, 상대를 가르치지 않고 곁에 머문다.

규칙:
- 정/역방향을 해석에 반드시 반영한다.
- 미래를 100% 확정하지 않는다. (가능성, 징조, 흐름)
- 공포 조장 금지.
- “~해야 한다” 같은 명령형 조언 금지.
- 번호, 불릿, 목록, 리포트형 소제목 금지.
- 줄바꿈은 허용하되 ‘자연스러운 문단’으로만 구성한다.
- 문단 흐름은: 오프닝 1문단 → 카드 흐름 2~3문단 → 마무리 1문단
- 전체 길이는 1100~1700자 정도로 충분히 길게. (짧게 끝내지 말 것)
- 달빛, 별, 안개, 문, 길, 숨결, 파도, 바람 같은 이미지를 자연스럽게 섞어라.
- 오프닝은 절대 똑같이 반복하지 말 것
- 특히 다음 문구/패턴 금지:
  "달빛이 부드럽게 내리쬐는 이 밤", "이 밤", "달빛 아래" 로 시작하는 고정 오프닝
- 마지막 문단은 ‘힘이 나는 위로와 축복’으로 마무리해라.
""".strip()

# =========================================================
# 유틸
# =========================================================
def now_utc():
    return datetime.utcnow()

def rate_limit_ok():
    calls = st.session_state.calls
    now = now_utc()
    cleaned = []
    for dt in calls:
        if now - dt < timedelta(seconds=60):
            cleaned.append(dt)
    if len(cleaned) >= MAX_CALLS_PER_MIN:
        st.session_state.calls = cleaned
        return False
    cleaned.append(now)
    st.session_state.calls = cleaned
    return True

def make_cache_key(question, cards):
    raw = question + "||" + "||".join([f"{c['name']}:{c['dir']}" for c in cards])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def call_model(question, cards):
    qmeta = classify_question(question)

    flavor_lines = []
    for c in cards:
        flavor_lines.append(
            f"{c['pos']} 카드 힌트: {c['name']} ({c['dir_kr']}) → {card_flavor_text(c['name'], c['dir_kr'])}"
        )
    flavor_block = "\n".join(flavor_lines)

    opening_style = random.choice(OPENING_STYLES)

    prompt = f"""
[오늘의 질문 테마]
- 테마: {qmeta['theme']}
- 목소리: {qmeta['voice']}
- 주의: {qmeta['caution']}

[오프닝 시작 스타일 지시]
{opening_style}

[질문]
{question}

[카드 힌트(문체/상징/온도)]
{flavor_block}

요청:
- 오프닝 문단에서 분위기를 잡고(신비롭게), 카드 흐름 문단에서 자연스럽게 과거→현재→미래의 결을 이어가고, 마지막 문단에서 따뜻하게 힘이 나도록 끝내라.
- 번호/불릿/리포트 금지. 문단(줄바꿈)만 허용.
- 단정하지 말고 ‘흐름’으로 말해라.
"""
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.95,
    )
    text = res.choices[0].message.content.strip()

    lines = text.splitlines()
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            cleaned.append("")
            continue
        for bad in ["1)", "2)", "3)", "4)", "1.", "2.", "3.", "4.", "•", "- "]:
            if s.startswith(bad):
                s = s[len(bad):].lstrip()
        cleaned.append(s)
    return "\n".join(cleaned).strip()

# =========================================================
# Streamlit UI
# =========================================================
st.set_page_config(page_title="미스틱 AI 타로관", page_icon="🔮", layout="centered")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700&family=Cinzel:wght@700&display=swap');

.stApp {{
  background-image: url("{BG_URL}");
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
}}
.stApp::before {{
  content: "";
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.6);
  pointer-events: none;
  z-index: 0;
}}
.block-container {{
  position: relative;
  z-index: 1;
}}
h1, h2, h3, p, div, span, label {{
  font-family: 'Nanum Myeongjo', serif;
}}
.title {{
  font-family: 'Cinzel', serif;
  text-align: center;
  font-size: 3rem;
  color: #f0e68c;
  text-shadow: 0 0 20px rgba(240,230,140,.8);
  margin: 10px 0 6px;
}}
.sub {{
  text-align: center;
  color: #f0e68c;
  margin-bottom: 10px;
  opacity: .95;
}}
.panel {{
  margin-top: 18px;
  padding: 20px;
  border-radius: 18px;
  border: 2px solid #d4af37;
  background: rgba(20,0,40,.85);
  line-height: 1.95;
  white-space: pre-wrap;
  color: #e0d4fc;
  box-shadow: 0 0 30px rgba(106,13,173,.35);
}}
.card {{
  height: 220px;
  border-radius: 16px;
  border: 2px solid #d4af37;
  background: linear-gradient(135deg,#2c003e,#000);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 6px;
  box-shadow: 0 10px 22px rgba(0,0,0,.55);
}}
.icon {{ font-size: 44px; color: #f0e68c; }}
.pos {{ font-size: 13px; color: #f0e68c; opacity:.95; font-weight:700; }}
.name {{ font-size: 15px; font-weight:700; color:#fff; }}
.dir {{ font-size: 13px; color:#f0e68c; opacity:.85; }}
.small {{
  margin-top: 14px;
  font-size: 12px;
  opacity: .7;
  text-align: center;
}}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="title">🔮 미스틱 AI 타로관</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">달빛 아래, 네 마음의 결을 읽어줄게.</div>', unsafe_allow_html=True)

question = st.text_input("질문", placeholder="지금 가장 마음에 남아 있는 질문은?", max_chars=220)

if st.button("세 장 뽑기"):
    if not question.strip():
        st.warning("질문을 먼저 적어줘.")
    elif not rate_limit_ok():
        st.error("너무 연속으로 뽑았어 😵‍💫 잠깐 숨 고르고 다시 해줘.")
    else:
        names = random.sample(tarot_deck, 3)
        positions = ["과거", "현재", "미래"]
        cards = []
        for name, pos in zip(names, positions):
            rev = random.choice([True, False])
            cards.append({
                "name": name,
                "pos": pos,
                "dir": "reversed" if rev else "upright",
                "dir_kr": "역방향" if rev else "정방향"
            })

        key = make_cache_key(question, cards)
        now = now_utc()
        cached = st.session_state.cache.get(key)

        if cached and cached[0] > now:
            reading = cached[1]
        else:
            with st.spinner("카드가 숨을 고르는 중…"):
                reading = call_model(question, cards)
            st.session_state.cache[key] = (now + timedelta(seconds=CACHE_TTL_SECONDS), reading)

        theme = classify_question(question)["theme"]
        st.markdown(f"<div class='sub'>오늘의 기운: {theme}</div>", unsafe_allow_html=True)

        icons = ["☾", "☀︎", "⭐︎"]
        cols = st.columns(3)
        for i, col in enumerate(cols):
            c = cards[i]
            with col:
                st.markdown(f"""
                <div class="card">
                  <div class="icon">{icons[i]}</div>
                  <div class="pos">{c['pos']}</div>
                  <div class="name">{c['name']}</div>
                  <div class="dir">{c['dir_kr']}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown(f"<div class='panel'>{reading}</div>", unsafe_allow_html=True)

st.markdown('<div class="small">※ 재미/성찰용입니다. 중요한 결정(의료/법률/투자 등)은 전문가 상담을 고려하세요.</div>', unsafe_allow_html=True)
