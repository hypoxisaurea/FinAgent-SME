import os
from pathlib import Path
import re

from langchain_core.tools import tool
import opendartreader as OpenDartReader
import pandas as pd
import requests

from backend_env import load_backend_env

load_backend_env()

ECOS_BASE = "https://ecos.bok.or.kr/api"

# ---------------------------------------------------------------------------
# CSV 파일 경로
# ---------------------------------------------------------------------------
DATA_DIR     = Path(__file__).parent / "data"
PROFIT_CSV   = DATA_DIR / "profit_ratio.csv"     # 한국은행 손익지표
ASSET_CSV    = DATA_DIR / "asset_ratio.csv"      # 한국은행 자산/자본지표
ACTIVITY_CSV = DATA_DIR / "activity_ratio.csv"   # 한국은행 활동성지표
GROWTH_CSV   = DATA_DIR / "growth_ratio.csv"     # 한국은행 성장성지표
AGRI_CSV     = DATA_DIR / "agri_production.csv"  # 농림업생산지수 (A01용)


# ===========================================================================
# 업종별 허용 범위 기준 (_compare 함수에서 사용)
# reverse=True  → 낮을수록 양호 (부채비율·차입금의존도)
# reverse=False → 높을수록 양호 (이익률·회전율 등)
# threshold     → 산업평균 대비 ±N 이내 = in-line
# ===========================================================================
_DEFAULT_THRESHOLDS: dict = {
    "debt_ratio":          {"reverse": True,  "threshold": 0.10},
    "borrow_dep":          {"reverse": True,  "threshold": 0.10},
    "current_ratio":       {"reverse": False, "threshold": 0.10},
    "op_margin":           {"reverse": False, "threshold": 0.10},
    "interest_coverage":   {"reverse": False, "threshold": 0.10},
    "receivable_turnover": {"reverse": False, "threshold": 0.10},
    "asset_turnover":      {"reverse": False, "threshold": 0.10},
    "sales_growth":        {"reverse": False, "threshold": 0.10},
}

_SECTOR_THRESHOLDS: dict[str, dict] = {
    "A01 농업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.30},
        "borrow_dep":          {"reverse": True,  "threshold": 0.30},
        "current_ratio":       {"reverse": False, "threshold": 0.25},
        "op_margin":           {"reverse": False, "threshold": 0.25},
        "interest_coverage":   {"reverse": False, "threshold": 0.30},
        "receivable_turnover": {"reverse": False, "threshold": 0.25},
        "asset_turnover":      {"reverse": False, "threshold": 0.25},
        "sales_growth":        {"reverse": False, "threshold": 0.30},
    },
    "A03 어업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.30},
        "borrow_dep":          {"reverse": True,  "threshold": 0.30},
        "current_ratio":       {"reverse": False, "threshold": 0.25},
        "op_margin":           {"reverse": False, "threshold": 0.25},
        "interest_coverage":   {"reverse": False, "threshold": 0.30},
        "receivable_turnover": {"reverse": False, "threshold": 0.25},
        "asset_turnover":      {"reverse": False, "threshold": 0.25},
        "sales_growth":        {"reverse": False, "threshold": 0.30},
    },
    "B 광업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.25},
        "borrow_dep":          {"reverse": True,  "threshold": 0.25},
        "current_ratio":       {"reverse": False, "threshold": 0.20},
        "op_margin":           {"reverse": False, "threshold": 0.20},
        "interest_coverage":   {"reverse": False, "threshold": 0.20},
        "receivable_turnover": {"reverse": False, "threshold": 0.20},
        "asset_turnover":      {"reverse": False, "threshold": 0.20},
        "sales_growth":        {"reverse": False, "threshold": 0.25},
    },
    "D35 전기, 가스, 증기 및 공기조절 공급업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.30},
        "borrow_dep":          {"reverse": True,  "threshold": 0.30},
        "current_ratio":       {"reverse": False, "threshold": 0.20},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.15},
        "receivable_turnover": {"reverse": False, "threshold": 0.20},
        "asset_turnover":      {"reverse": False, "threshold": 0.25},
        "sales_growth":        {"reverse": False, "threshold": 0.20},
    },
    "E37-39 하수 · 폐기물 처리, 원료재생업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.20},
        "borrow_dep":          {"reverse": True,  "threshold": 0.20},
        "current_ratio":       {"reverse": False, "threshold": 0.15},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.15},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.20},
        "sales_growth":        {"reverse": False, "threshold": 0.20},
    },
    "F 건설업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.30},
        "borrow_dep":          {"reverse": True,  "threshold": 0.30},
        "current_ratio":       {"reverse": False, "threshold": 0.20},
        "op_margin":           {"reverse": False, "threshold": 0.20},
        "interest_coverage":   {"reverse": False, "threshold": 0.20},
        "receivable_turnover": {"reverse": False, "threshold": 0.20},
        "asset_turnover":      {"reverse": False, "threshold": 0.20},
        "sales_growth":        {"reverse": False, "threshold": 0.25},
    },
    "G 도매 및 소매업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.15},
        "borrow_dep":          {"reverse": True,  "threshold": 0.15},
        "current_ratio":       {"reverse": False, "threshold": 0.10},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.15},
        "receivable_turnover": {"reverse": False, "threshold": 0.10},
        "asset_turnover":      {"reverse": False, "threshold": 0.10},
        "sales_growth":        {"reverse": False, "threshold": 0.10},
    },
    "H 운수 및 창고업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.25},
        "borrow_dep":          {"reverse": True,  "threshold": 0.25},
        "current_ratio":       {"reverse": False, "threshold": 0.15},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.15},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.15},
        "sales_growth":        {"reverse": False, "threshold": 0.15},
    },
    "I 숙박 및 음식점업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.25},
        "borrow_dep":          {"reverse": True,  "threshold": 0.25},
        "current_ratio":       {"reverse": False, "threshold": 0.20},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.20},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.15},
        "sales_growth":        {"reverse": False, "threshold": 0.20},
    },
    "J 정보통신업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.10},
        "borrow_dep":          {"reverse": True,  "threshold": 0.10},
        "current_ratio":       {"reverse": False, "threshold": 0.10},
        "op_margin":           {"reverse": False, "threshold": 0.10},
        "interest_coverage":   {"reverse": False, "threshold": 0.10},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.15},
        "sales_growth":        {"reverse": False, "threshold": 0.10},
    },
    "L 부동산업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.35},
        "borrow_dep":          {"reverse": True,  "threshold": 0.35},
        "current_ratio":       {"reverse": False, "threshold": 0.25},
        "op_margin":           {"reverse": False, "threshold": 0.20},
        "interest_coverage":   {"reverse": False, "threshold": 0.25},
        "receivable_turnover": {"reverse": False, "threshold": 0.25},
        "asset_turnover":      {"reverse": False, "threshold": 0.25},
        "sales_growth":        {"reverse": False, "threshold": 0.25},
    },
    "M 전문, 과학 및 기술 서비스업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.15},
        "borrow_dep":          {"reverse": True,  "threshold": 0.15},
        "current_ratio":       {"reverse": False, "threshold": 0.10},
        "op_margin":           {"reverse": False, "threshold": 0.10},
        "interest_coverage":   {"reverse": False, "threshold": 0.10},
        "receivable_turnover": {"reverse": False, "threshold": 0.10},
        "asset_turnover":      {"reverse": False, "threshold": 0.10},
        "sales_growth":        {"reverse": False, "threshold": 0.10},
    },
    "N 사업시설 관리 및 사업지원 및 임대 서비스업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.15},
        "borrow_dep":          {"reverse": True,  "threshold": 0.15},
        "current_ratio":       {"reverse": False, "threshold": 0.15},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.15},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.15},
        "sales_growth":        {"reverse": False, "threshold": 0.15},
    },
    "P 교육 서비스업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.15},
        "borrow_dep":          {"reverse": True,  "threshold": 0.15},
        "current_ratio":       {"reverse": False, "threshold": 0.20},
        "op_margin":           {"reverse": False, "threshold": 0.10},
        "interest_coverage":   {"reverse": False, "threshold": 0.10},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.15},
        "sales_growth":        {"reverse": False, "threshold": 0.10},
    },
    "R 예술, 스포츠 및 여가관련 서비스업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.25},
        "borrow_dep":          {"reverse": True,  "threshold": 0.25},
        "current_ratio":       {"reverse": False, "threshold": 0.20},
        "op_margin":           {"reverse": False, "threshold": 0.20},
        "interest_coverage":   {"reverse": False, "threshold": 0.20},
        "receivable_turnover": {"reverse": False, "threshold": 0.20},
        "asset_turnover":      {"reverse": False, "threshold": 0.20},
        "sales_growth":        {"reverse": False, "threshold": 0.20},
    },
    "S95 개인 및 소비용품 수리업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.15},
        "borrow_dep":          {"reverse": True,  "threshold": 0.15},
        "current_ratio":       {"reverse": False, "threshold": 0.15},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.15},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.15},
        "sales_growth":        {"reverse": False, "threshold": 0.15},
    },
    "S96 기타 개인 서비스업": {
        "debt_ratio":          {"reverse": True,  "threshold": 0.15},
        "borrow_dep":          {"reverse": True,  "threshold": 0.15},
        "current_ratio":       {"reverse": False, "threshold": 0.15},
        "op_margin":           {"reverse": False, "threshold": 0.15},
        "interest_coverage":   {"reverse": False, "threshold": 0.15},
        "receivable_turnover": {"reverse": False, "threshold": 0.15},
        "asset_turnover":      {"reverse": False, "threshold": 0.15},
        "sales_growth":        {"reverse": False, "threshold": 0.15},
    },
}


# ===========================================================================
# 업종별 주의사항 텍스트
# ===========================================================================
_SECTOR_NOTES: dict[str, str] = {
    "A01 농업":
        "기후·계절성 리스크 내재. 재고자산(농산물) 변동성 크고 매출 계절집중. "
        "정부 수매·보조금 정책이 수익성에 직접 영향.",
    "A03 어업":
        "어획 쿼터·수산자원 규제 및 해수온 변화 리스크. "
        "수출 비중 높아 환율·검역 이슈 주의. 선박 감가상각으로 고정비 부담 큼.",
    "B 광업":
        "국제 원자재 가격 연동성 높음. 탐사·개발 단계 CAPEX 집중으로 "
        "초기 부채비율 급등 가능. 자원 고갈 리스크 장기 반영 필요.",
    "C 제조업":
        "원가 구조(원자재·인건비)와 재고 회전율이 수익성 핵심. "
        "환율 민감도 높고 글로벌 공급망 리스크 존재. "
        "설비 투자 주기에 따라 FCF 급변 가능.",
    "D35 전기, 가스, 증기 및 공기조절 공급업":
        "가격 규제 산업으로 수익성 상한 존재. LNG·석탄 수입 의존으로 원가 변동성 높음. "
        "설비 투자 규모 크고 장기 차입 비중 높은 구조 정상.",
    "E37-39 하수 · 폐기물 처리, 원료재생업":
        "정책·환경규제 연동 방어형 업종. 경기 둔감형으로 안정적 현금흐름. "
        "ESG 수혜 업종이나 처리 단가 규제 리스크 존재.",
    "F 건설업":
        "부채비율 200% 이상도 업종 특성상 정상 범위. "
        "수주잔고·원가율(매출원가율) 중점 확인. "
        "준공 시점 매출 집중으로 분기 변동성 큼. PF 연대보증 우발채무 주의.",
    "G 도매 및 소매업":
        "매출채권·재고 회전율이 유동비율보다 중요한 건전성 지표. "
        "온라인 채널 전환 여부와 플랫폼 의존도 확인. "
        "저마진-고회전 구조로 영업이익률 낮아도 정상일 수 있음.",
    "H 운수 및 창고업":
        "유가·물동량 연동으로 수익성 변동. 차량·선박 등 유형자산 비중 높아 "
        "영업레버리지 큼. 안전 규제 준수 비용 내재.",
    "I 숙박 및 음식점업":
        "객실·좌석 가동률과 객단가가 수익성 핵심. "
        "선수금(예약금)이 유동부채 증가 원인 → 유동비율 낮아도 실질 위험 아닐 수 있음. "
        "경기 민감형으로 소비심리 지표 연계 확인.",
    "J 정보통신업":
        "인건비 집약 구조. 유형자산 적어 부채비율·차입금의존도 낮아야 정상. "
        "클라우드·구독형 전환 시 초기 매출 인식 방식 변화 주의. "
        "특허·SW 등 무형자산 가치 재무제표 미반영 리스크.",
    "L 부동산업":
        "레버리지 높은 구조가 업종 기본. 담보자산(토지·건물) 대비 차입금 비율 핵심. "
        "금리 민감도 매우 높음. 개발사업 단계별 수익 인식 불일치 주의.",
    "M 전문, 과학 및 기술 서비스업":
        "인적 자산 집약형. 매출채권 관리가 유동성 핵심. "
        "프로젝트 기반 매출로 계절성·수주 편중 리스크. "
        "고숙련 인력 이탈이 실질적 최대 리스크.",
    "N 사업시설 관리 및 사업지원 및 임대 서비스업":
        "계약 기반 안정 매출 구조. 인건비 비중 높아 최저임금 인상 영향 직접 수령. "
        "임대업(N76)은 L 부동산업과 유사한 레버리지 특성.",
    "P 교육 서비스업":
        "수강료 선수금이 유동부채 증가 요인 → 유동비율 낮아도 실질 위험 낮을 수 있음. "
        "학령인구 감소 장기 구조적 리스크. "
        "온라인 전환 가속화로 고정비(임대·강사) 구조 변화 중.",
    "R 예술, 스포츠 및 여가관련 서비스업":
        "경기 민감형 소비 업종. 시설 투자 주기(3~5년)에 따라 부채 급등 가능. "
        "IP·저작권 자산 가치 미반영. 공연·스포츠는 날씨·이벤트 의존도 높음.",
    "S95 개인 및 소비용품 수리업":
        "소규모·현금 거래 중심으로 매출 과소 계상 리스크 존재. "
        "전문 기술 인력 의존도 높아 인건비 비중 큼.",
    "S96 기타 개인 서비스업":
        "경기 민감형 소비 서비스. 고정비(임대·인건) 부담 관리가 생존 핵심. "
        "진입장벽 낮아 경쟁 심화 구조.",
}


# ===========================================================================
# 업종별 환율 민감도
# ===========================================================================
_FX_SENSITIVITY: dict[str, str] = {
    "A01 농업":                                            "수입의존형",
    "A03 어업":                                            "수출형",
    "B 광업":                                              "내수형",
    "C 제조업":                                            "수출형",
    "D35 전기, 가스, 증기 및 공기조절 공급업":             "원자재수입형",
    "E37-39 하수 · 폐기물 처리, 원료재생업":               "내수형",
    "F 건설업":                                            "내수형",
    "G 도매 및 소매업":                                    "수입의존형",
    "H 운수 및 창고업":                                    "수출형",
    "I 숙박 및 음식점업":                                  "내수형",
    "J 정보통신업":                                        "중립형",
    "L 부동산업":                                          "내수형",
    "M 전문, 과학 및 기술 서비스업":                       "중립형",
    "N 사업시설 관리 및 사업지원 및 임대 서비스업":        "내수형",
    "P 교육 서비스업":                                     "내수형",
    "R 예술, 스포츠 및 여가관련 서비스업":                 "내수형",
    "S95 개인 및 소비용품 수리업":                         "내수형",
    "S96 기타 개인 서비스업":                              "내수형",
}


# ===========================================================================
# KOSIS 서비스업생산지수 업종명 키워드 매핑
# (DT_1KC2020 응답의 C1_NM 필드에서 해당 키워드가 포함된 행 필터링)
# ===========================================================================
_KSIC_TO_KOSIS_SVC_KW: dict[str, str] = {
    "E37-39 하수 · 폐기물 처리, 원료재생업":           "수도 하수 및 폐기물 처리 원료 재생업",
    "G 도매 및 소매업":                                "도매 및 소매업",
    "H 운수 및 창고업":                                "운수 및 창고업",
    "I 숙박 및 음식점업":                              "숙박 및 음식점업",
    "J 정보통신업":                                    "정보통신업",
    "L 부동산업":                                      "부동산업",
    "M 전문, 과학 및 기술 서비스업":                   "전문 과학 및 기술 서비스업",
    "N 사업시설 관리 및 사업지원 및 임대 서비스업":    "사업시설 관리 사업지원 및 임대 서비스업",
    "P 교육 서비스업":                                 "교육 서비스업",
    "R 예술, 스포츠 및 여가관련 서비스업":             "예술 스포츠 및 여가 관련 서비스업",
    "S95 개인 및 소비용품 수리업":                     "개인 및 소비용품 수리업",
    "S96 기타 개인 서비스업":                          "기타 개인 서비스업",
}


# ===========================================================================
# DART induty_code 앞 2자리 → KSIC 대분류
# ===========================================================================
_INDUTY_TO_KSIC = {
    "01": "A01 농업",
    "02": None,
    "03": "A03 어업",
    "05": "B 광업", "06": "B 광업", "07": "B 광업", "08": "B 광업",
    "10": "C 제조업", "11": "C 제조업", "12": "C 제조업",
    "13": "C 제조업", "14": "C 제조업", "15": "C 제조업",
    "16": "C 제조업", "17": "C 제조업", "18": "C 제조업",
    "19": "C 제조업", "20": "C 제조업", "21": "C 제조업",
    "22": "C 제조업", "23": "C 제조업", "24": "C 제조업",
    "25": "C 제조업", "26": "C 제조업", "27": "C 제조업",
    "28": "C 제조업", "29": "C 제조업", "30": "C 제조업",
    "31": "C 제조업", "32": "C 제조업", "33": "C 제조업",
    "34": "C 제조업",
    "35": "D35 전기, 가스, 증기 및 공기조절 공급업",
    "36": None,
    "37": "E37-39 하수 · 폐기물 처리, 원료재생업",
    "38": "E37-39 하수 · 폐기물 처리, 원료재생업",
    "39": "E37-39 하수 · 폐기물 처리, 원료재생업",
    "41": "F 건설업", "42": "F 건설업",
    "45": "G 도매 및 소매업", "46": "G 도매 및 소매업", "47": "G 도매 및 소매업",
    "49": "H 운수 및 창고업", "50": "H 운수 및 창고업",
    "51": "H 운수 및 창고업", "52": "H 운수 및 창고업",
    "55": "I 숙박 및 음식점업", "56": "I 숙박 및 음식점업",
    "58": "J 정보통신업", "59": "J 정보통신업", "60": "J 정보통신업",
    "61": "J 정보통신업", "62": "J 정보통신업", "63": "J 정보통신업",
    "64": None, "65": None, "66": None,
    "68": "L 부동산업",
    "70": None,
    "71": "M 전문, 과학 및 기술 서비스업",
    "72": "M 전문, 과학 및 기술 서비스업",
    "73": "M 전문, 과학 및 기술 서비스업",
    "74": "N 사업시설 관리 및 사업지원 및 임대 서비스업",
    "75": "N 사업시설 관리 및 사업지원 및 임대 서비스업",
    "76": "N 사업시설 관리 및 사업지원 및 임대 서비스업",
    "84": None,
    "85": "P 교육 서비스업",
    "86": None, "87": None,
    "90": "R 예술, 스포츠 및 여가관련 서비스업",
    "91": "R 예술, 스포츠 및 여가관련 서비스업",
    "94": None,
    "95": "S95 개인 및 소비용품 수리업",
    "96": "S96 기타 개인 서비스업",
    "97": None, "98": None, "99": None,
}


# ===========================================================================
# 내부 헬퍼
# ===========================================================================
def _get_dart():
    api_key = os.getenv("OPEN_DART_API_KEY", "").strip()
    if not api_key:
        raise ValueError("환경변수 OPEN_DART_API_KEY가 설정되지 않았습니다.")
    return OpenDartReader.OpenDartReader(api_key)


def _ecos_get(stat_code: str, item_code: str, period: str) -> list[dict]:
    api_key = os.environ.get("ECOS_API_KEY")
    if not api_key:
        raise ValueError("환경변수 ECOS_API_KEY가 설정되지 않았습니다.")
    url = (
        f"{ECOS_BASE}/StatisticSearch/{api_key}/json/kr/1/100"
        f"/{stat_code}/A/{period}/{period}/{item_code}"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return res.json().get("StatisticSearch", {}).get("row", [])


def _read_csv_val(csv_path: Path, account_nm: str,
                  ksic_code: str, year_str: str) -> float | None:
    """기업경영분석 CSV에서 단일 지표값 조회."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df_f = df[
        (df["업종코드"].str.strip() == ksic_code) &
        (df["계정항목"].str.strip() == account_nm) &
        (df["기업규모"].str.strip() == "중소기업")
    ]
    if df_f.empty or year_str not in df_f.columns:
        return None
    val = df_f.iloc[0][year_str]
    return float(val) if pd.notna(val) else None


def _compare(company_val: float | None, avg_val: float | None,
             reverse: bool, threshold: float) -> str:
    """기업값 vs 산업평균 비교 → above/in-line/below/n/a.
    reverse=True : 낮을수록 양호 (부채비율 등)
    reverse=False: 높을수록 양호 (이익률 등)
    """
    if avg_val is None or avg_val == 0 or company_val is None:
        return "n/a"
    ratio = company_val / avg_val
    if reverse:
        if ratio < 1 - threshold: return "better" # 낮아서 좋으니까 better
        if ratio > 1 + threshold: return "worse" # 높아서 나쁘니까 worse
    else:
        if ratio > 1 + threshold: return "better" # 높아서 좋으니까 better
        if ratio < 1 - threshold: return "worse"  # 낮아서 나쁘니까 worse
    return "in-line"


def _score_from_yoy(prod_yoy: float | None) -> str:
    """생산지수 YoY → 업황 등급.
    Low  (업황 양호): YoY ≥ +3%
    Medium           : -3% ≤ YoY < +3%
    High (업황 부진): YoY < -3%
    ※ ±3%는 서비스·비제조 업종 초기 임계값. 업종별 튜닝 필요 시 별도 dict로 교체.
    """
    if prod_yoy is None:
        return "Medium"
    if prod_yoy >= 0.03:  return "Low"
    if prod_yoy >= -0.03: return "Medium"
    return "High"


def _kosis_param_query(tbl_id: str, itm_id: str = "ALL",
                       obj_l1: str = "ALL", count: int = 13) -> list[dict]:
    """KOSIS Param API 공통 쿼리."""
    api_key = os.environ.get("KOSIS_API_KEY")
    if not api_key:
        return []
    url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    params = {
        "method": "getList", "apiKey": api_key,
        "itmId": itm_id, "objL1": obj_l1,
        "format": "json", "jsonVD": "Y",
        "prdSe": "M", "newEstPrdCnt": str(count),
        "orgId": "101", "tblId": tbl_id,
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _extract_yoy_from_rows(rows: list[dict], name_keyword: str,
                            itm_keyword: str = "불변") -> float | None:
    """KOSIS 응답 rows에서 업종명·항목명 키워드로 필터 후 YoY 계산."""
    vals: list[tuple[str, float]] = []
    for row in rows:
        c1_nm  = str(row.get("C1_NM") or row.get("C1_OBJ_NM") or "")
        itm_nm = str(row.get("ITM_NM")    or row.get("ITM_ID") or "")
        prd    = str(row.get("PRD_DE")    or "")
        if name_keyword not in c1_nm:
            continue
        if itm_keyword and itm_keyword not in itm_nm:
            continue
        try:
            dt = float(row.get("DT") or 0)
            if dt > 0 and prd:
                vals.append((prd, dt))
        except (ValueError, TypeError):
            continue
    vals.sort(key=lambda x: x[0])
    if len(vals) < 13:
        return None
    prev, curr = vals[-13][1], vals[-1][1]
    return (curr - prev) / prev if prev != 0 else None


def _read_agri_yoy() -> float | None:
    """농림업생산지수 CSV에서 농업총계 연간 YoY 계산.
    CSV 형식: 행=품목별, 열=연도(YYYY)+생산금액(YYYY.1)
    """
    if not AGRI_CSV.exists():
        return None
    try:
        df = pd.read_csv(AGRI_CSV, encoding="cp949")
    except Exception:
        try:
            df = pd.read_csv(AGRI_CSV, encoding="utf-8-sig")
        except Exception:
            return None

    # 단위 헤더 행(품목별='품목별') 제거
    df = df[df.iloc[:, 0].astype(str).str.strip() != "품목별"].copy()

    row = df[df.iloc[:, 0].astype(str).str.strip() == "농업총계"]
    if row.empty:
        return None
    row = row.iloc[0]

    # 생산지수 컬럼: 4자리 순수 연도 (YYYY.1 형태의 생산금액 컬럼 제외)
    prod_cols = sorted(
        [c for c in df.columns if re.fullmatch(r"\d{4}", str(c))],
        key=lambda x: int(x)
    )
    if len(prod_cols) < 2:
        return None
    try:
        prev = float(row[prod_cols[-2]])
        curr = float(row[prod_cols[-1]])
        return (curr - prev) / prev if prev != 0 else None
    except (ValueError, TypeError):
        return None


# ===========================================================================
# TOOLS
# ===========================================================================

@tool
def map_corp_to_ksic(corp_code: str) -> str:
    """DART 회사개황의 업종코드를 KSIC 코드로 변환."""
    dart = _get_dart()
    info = dart.company(corp_code)
    if info is None:
        raise ValueError(f"corp_code={corp_code} 회사 정보 없음")
    induty = str(info.get("induty_code", ""))
    ksic = _INDUTY_TO_KSIC.get(induty[:2])
    if ksic is None:
        return f"N/A (업종코드 {induty} - 산업평균 데이터 없음)"
    return ksic


@tool
def get_industry_avg_ratios(
    ksic_code: str,
    year: int,
    company_ratios: dict = None,
) -> dict:
    """한국은행 기업경영분석 CSV에서 KSIC 업종 중소기업 평균 재무비율 조회.

    지표: 영업이익률, 부채비율, 유동비율, 이자보상비율, 차입금의존도,
          매출채권회전율, 총자산회전율, 매출액증가율

    company_ratios 전달 시 업종별 허용범위 기준으로 peer_comparison 포함 반환.
    company_ratios 키: debt_ratio, current_ratio, op_margin,
                       interest_coverage, borrow_dep,
                       receivable_turnover, asset_turnover, sales_growth
    """
    if ksic_code.startswith("N/A"):
        return {
            "avg_op_margin": None, "avg_debt_ratio": None,
            "avg_current_ratio": None, "avg_interest_coverage": None,
            "avg_borrow_dep": None, "avg_receivable_turnover": None,
            "avg_asset_turnover": None, "avg_sales_growth": None,
            "ksic_code": ksic_code, "year": year,
            "note": "산업평균 데이터 없음",
            "sector_note": _SECTOR_NOTES.get(ksic_code, ""),
        }

    AVAILABLE_YEARS = ["2012","2013","2014","2015","2016","2017",
                   "2018","2019","2020","2021","2022","2023","2024"]
    year_str = str(year) if str(year) in AVAILABLE_YEARS else str(
        max(int(y) for y in AVAILABLE_YEARS if int(y) <= year)
    )

    def _r(path, nm):
        v = _read_csv_val(path, nm, ksic_code, year_str)
        return v / 100 if v is not None else None

    avg = {
        "avg_op_margin":           _r(PROFIT_CSV,   "매출액영업이익률"),
        "avg_debt_ratio":          _r(ASSET_CSV,    "부채비율"),
        "avg_current_ratio":       _r(ASSET_CSV,    "유동비율"),
        "avg_interest_coverage":   _r(PROFIT_CSV,   "이자보상비율"),
        "avg_borrow_dep":          _r(ASSET_CSV,    "차입금의존도"),
        "avg_receivable_turnover": _read_csv_val(ACTIVITY_CSV, "매출채권회전율", ksic_code, year_str),
        "avg_asset_turnover":      _read_csv_val(ACTIVITY_CSV, "총자산회전율",   ksic_code, year_str),
        "avg_sales_growth":        _r(GROWTH_CSV,   "매출액증가율"),
        "ksic_code":   ksic_code,
        "year":        year,
        "sector_note": _SECTOR_NOTES.get(ksic_code, ""),
    }

    if company_ratios:
        thresholds = _SECTOR_THRESHOLDS.get(ksic_code, _DEFAULT_THRESHOLDS)

        def _cmp(key, avg_key):
            return _compare(
                company_ratios.get(key),
                avg.get(avg_key),
                reverse=thresholds[key]["reverse"],
                threshold=thresholds[key]["threshold"],
            )

        avg["peer_comparison"] = {
            "debt_ratio":          _cmp("debt_ratio",          "avg_debt_ratio"),
            "current_ratio":       _cmp("current_ratio",       "avg_current_ratio"),
            "op_margin":           _cmp("op_margin",           "avg_op_margin"),
            "interest_coverage":   _cmp("interest_coverage",   "avg_interest_coverage"),
            "borrow_dep":          _cmp("borrow_dep",          "avg_borrow_dep"),
            "receivable_turnover": _cmp("receivable_turnover", "avg_receivable_turnover"),
            "asset_turnover":      _cmp("asset_turnover",      "avg_asset_turnover"),
            "sales_growth":        _cmp("sales_growth",        "avg_sales_growth"),
        }

    return avg


@tool
def get_industry_outlook(ksic_code: str) -> dict:
    """업종별 생산지수로 업황 등급 산출.

    ┌──────────────────────────────┬──────────────────────────────────────┐
    │ 업종                         │ 소스                                 │
    ├──────────────────────────────┼──────────────────────────────────────┤
    │ B 광업 / C 제조업            │ KOSIS 광공업생산지수 (생산+재고+출하) │
    │ E G H I J L M N P R S       │ KOSIS 서비스업생산지수 (불변지수)     │
    │ F 건설업                     │ KOSIS 전산업생산지수 (건설업 행)      │
    │ A01 농업                     │ 농림업생산지수 CSV (농업총계 행)      │
    │ A03 어업 / D35 전기가스      │ 데이터 없음 → Medium                 │
    └──────────────────────────────┴──────────────────────────────────────┘
    """
    # ── ① KOSIS 광공업: B 광업 + C 제조업 ─────────────────────────────────
    if ksic_code.startswith("B ") or ksic_code.startswith("C "):
        rows = _kosis_param_query("DT_1F02011", itm_id="T10 T11 T12")
        if not rows:
            return {"outlook_score": "Medium", "source": "KOSIS 광공업(오류-중립)"}

        prod_v, inv_v, ship_v = [], [], []
        for row in rows:
            itm = row.get("ITM_ID", "")
            val = float(row.get("DT", 0) or 0)
            if itm == "T10":   prod_v.append(val)
            elif itm == "T11": inv_v.append(val)
            elif itm == "T12": ship_v.append(val)

        def _yoy(vals):
            return (vals[-1] - vals[-13]) / vals[-13] if len(vals) >= 13 else 0.0

        prod_yoy = _yoy(prod_v)
        inv_yoy  = _yoy(inv_v)
        ship_yoy = _yoy(ship_v)

        if   prod_yoy <= -0.10 and inv_yoy > 0:    score = "High"
        elif prod_yoy <= -0.05 or  inv_yoy > 0.05: score = "Medium"
        else:                                        score = "Low"

        return {
            "production_index_yoy": round(prod_yoy,  4),
            "inventory_index_yoy":  round(inv_yoy,   4),
            "shipment_index_yoy":   round(ship_yoy,  4),
            "outlook_score":        score,
            "source":               "KOSIS 광공업생산지수",
        }

    # ── ② KOSIS 서비스업: E G H I J L M N P R S ────────────────────────────
    if ksic_code in _KSIC_TO_KOSIS_SVC_KW:
        keyword = _KSIC_TO_KOSIS_SVC_KW[ksic_code]
        rows    = _kosis_param_query("DT_1KC2020")
        prod_yoy = _extract_yoy_from_rows(rows, keyword, itm_keyword="불변")
        if prod_yoy is None:
            # 불변지수 없을 시 항목 무관하게 재시도
            prod_yoy = _extract_yoy_from_rows(rows, keyword, itm_keyword="")
        return {
            "production_index_yoy": round(prod_yoy, 4) if prod_yoy is not None else None,
            "inventory_index_yoy":  None,
            "shipment_index_yoy":   None,
            "outlook_score":        _score_from_yoy(prod_yoy),
            "source":               "KOSIS 서비스업생산지수" if prod_yoy is not None
                                    else "KOSIS 서비스업생산지수(데이터 없음-중립)",
        }

    # ── ③ KOSIS 전산업생산지수: F 건설업 ──────────────────────────────────
    # tblId: KOSIS 홈페이지 전산업생산지수 > OPENAPI 버튼에서 확인
    if ksic_code == "F 건설업":
        rows     = _kosis_param_query("DT_1KE10041")
        prod_yoy = _extract_yoy_from_rows(rows, "건설업", itm_keyword="")
        return {
            "production_index_yoy": round(prod_yoy, 4) if prod_yoy is not None else None,
            "inventory_index_yoy":  None,
            "shipment_index_yoy":   None,
            "outlook_score":        _score_from_yoy(prod_yoy),
            "source":               "KOSIS 전산업생산지수" if prod_yoy is not None
                                    else "KOSIS 전산업생산지수(tblId 확인 필요-중립)",
        }

    # ── ④ 농림업생산지수 CSV: A01 농업 ────────────────────────────────────
    if ksic_code == "A01 농업":
        prod_yoy = _read_agri_yoy()
        return {
            "production_index_yoy": round(prod_yoy, 4) if prod_yoy is not None else None,
            "inventory_index_yoy":  None,
            "shipment_index_yoy":   None,
            "outlook_score":        _score_from_yoy(prod_yoy),
            "source":               "농림업생산지수 CSV (농업총계)" if prod_yoy is not None
                                    else "농림업생산지수 CSV 없음 - 중립",
        }

    # ── ⑤ None 처리: A03 어업 / D35 전기가스 ─────────────────────────────
    return {
        "production_index_yoy": None,
        "inventory_index_yoy":  None,
        "shipment_index_yoy":   None,
        "outlook_score":        "Medium",
        "source":               "N/A",
        "note":                 f"{ksic_code} 생산지수 데이터 없음 - 중립(Medium) 적용",
    }


@tool
def get_business_cycle() -> dict:
    """한국은행 ECOS에서 선행·동행종합지수 순환변동치 조회 → 경기 국면 판단.

    국면:
    - 확장: 동행↑ + 선행↑
    - 회복: 동행↓ + 선행↑  (바닥 탈출)
    - 둔화: 동행↑ + 선행↓  (정점 근접)
    - 수축: 동행↓ + 선행↓
    """
    api_key = os.environ.get("ECOS_API_KEY")
    if not api_key:
        raise ValueError("환경변수 ECOS_API_KEY가 설정되지 않았습니다.")

    from datetime import date
    end = date.today().strftime("%Y%m")
    start = str(int(end[:4]) - 2) + end[4:]  # 2년치 확보
    
    def _fetch(item_code: str) -> list[float]:
        url = (
            f"{ECOS_BASE}/StatisticSearch/{api_key}/json/kr/1/24"
            f"/901Y067/M/{start}/{end}/{item_code}"
        )
        res = requests.get(url, timeout=10)
        rows = res.json().get("StatisticSearch", {}).get("row", [])
        return [float(r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE")]

    leading    = _fetch("I16A")
    coincident = _fetch("I16B")

    def _trend(vals: list[float]) -> str:
        if len(vals) < 6:
            return "unknown"
        return "rising" if sum(vals[-3:]) / 3 > sum(vals[-6:-3]) / 3 else "falling"

    lead_trend = _trend(leading)
    coin_trend = _trend(coincident)

    if   coin_trend == "rising"  and lead_trend == "rising":  phase = "확장"
    elif coin_trend == "falling" and lead_trend == "rising":  phase = "회복"
    elif coin_trend == "rising"  and lead_trend == "falling": phase = "둔화"
    else:                                                       phase = "수축"

    return {
        "leading_latest":       round(leading[-1],    2) if leading    else None,
        "coincident_latest":    round(coincident[-1], 2) if coincident else None,
        "leading_trend":        lead_trend,
        "coincident_trend":     coin_trend,
        "business_cycle_phase": phase,
    }


@tool
def get_macro_indicators(ksic_code: str = "") -> dict:
    """한국은행 ECOS에서 기준금리·원달러환율 최근치 조회.
    ksic_code 전달 시 업종별 환율 영향 해석 포함.
    """
    api_key = os.environ.get("ECOS_API_KEY")
    if not api_key:
        raise ValueError("환경변수 ECOS_API_KEY가 설정되지 않았습니다.")

    from datetime import date, timedelta

    # ── 기준금리 (연간) ─────────────────────────────────────────
    current_year = str(date.today().year)
    rate_rows = _ecos_get("722Y001", "0101000", current_year)
    # 당해년도 데이터 없으면 전년도로 fallback
    if not rate_rows:
        rate_rows = _ecos_get("722Y001", "0101000", str(date.today().year - 1))
    base_rate = float(rate_rows[-1]["DATA_VALUE"]) if rate_rows else None
    trend = "stable"
    if len(rate_rows) >= 2:
        diff = float(rate_rows[-1]["DATA_VALUE"]) - float(rate_rows[-2]["DATA_VALUE"])
        trend = "rising" if diff > 0 else ("falling" if diff < 0 else "stable")

    # ── 원달러 환율 (일별, 최근 30일 범위에서 최신 5건) ─────────
    today      = date.today()
    end_date   = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
    url = (
        f"{ECOS_BASE}/StatisticSearch/{api_key}/json/kr/1/5"
        f"/731Y001/D/{start_date}/{end_date}/0000001"
    )
    res = requests.get(url, timeout=10)
    fx_rows = res.json().get("StatisticSearch", {}).get("row", [])
    usd_krw = float(fx_rows[-1]["DATA_VALUE"]) if fx_rows else None

    result: dict = {"base_rate": base_rate, "usd_krw": usd_krw, "rate_trend": trend}

    if ksic_code:
        fx_type = _FX_SENSITIVITY.get(ksic_code, "중립형")
        result["fx_sensitivity"] = fx_type

        if   usd_krw and usd_krw > 1350: fx_dir = "원화 약세"
        elif usd_krw and usd_krw < 1200: fx_dir = "원화 강세"
        else:                             fx_dir = "원화 중립"

        _impact: dict[str, dict[str, str]] = {
            "수출형":       {"원화 약세": "긍정적 (수출 경쟁력↑, 원화 환산 매출↑)",
                            "원화 강세": "부정적 (수출 마진·달러매출↓)",
                            "원화 중립": "중립"},
            "수입의존형":   {"원화 약세": "부정적 (수입 원가↑)",
                            "원화 강세": "긍정적 (수입 원가↓)",
                            "원화 중립": "중립"},
            "원자재수입형": {"원화 약세": "부정적 (원자재·에너지 비용↑)",
                            "원화 강세": "긍정적 (원자재 비용↓)",
                            "원화 중립": "중립"},
            "내수형":       {"원화 약세": "중립 (직접 영향 낮음, 수입물가 간접 영향)",
                            "원화 강세": "중립 (직접 영향 낮음)",
                            "원화 중립": "중립"},
            "중립형":       {"원화 약세": "중립", "원화 강세": "중립", "원화 중립": "중립"},
        }
        result["fx_direction"] = fx_dir
        result["fx_impact"]    = _impact.get(fx_type, {}).get(fx_dir, "중립")

    return result
