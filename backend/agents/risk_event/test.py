import sys

sys.path.insert(0, r"C:\2026\FinAgent-SME")

from backend.agents.risk_event.handlers.keyword_detector import detect_keywords

result = detect_keywords(
    company_name="케이씨피드",
    news_data=[
        {
            "title": "케이씨피드 부도 위기설 확산",
            "content": "최근 케이씨피드가 소송에 휘말리며 경영 위기가 가시화되고 있다.",
            "published_at": "2026-05-16",
            "url": "https://example.com"
        },
        {
            "title": "케이씨피드 2분기 실적 호조",
            "content": "케이씨피드가 2분기 매출 성장세를 기록했다.",
            "published_at": "2026-05-10",
            "url": "https://example.com/2"
        }
    ],
    disclosure_data=[
        {
            "title": "단기차입금 증가 관련 주요사항보고서",
            "content": "당사는 운영자금 확보를 위해 단기차입금을 증가하였습니다.",
            "disclosed_at": "2026-05-01",
            "url": "https://dart.fss.or.kr/example"
        }
    ],
)

print("== 키워드 탐지 결과 ==")
print(f"기업명: {result.company_name}")
print(f"탐지된 이벤트 수: {len(result.detected_events)}")
for event in result.detected_events:
    print(f"  - [{event.source.value}] {event.title}")
    print(f"    {event.description}")