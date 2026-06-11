from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests
from backend.common.api_client import build_llm_client_kwargs, get_model_name
from backend.common.env import load_backend_env
from backend.common.langfuse import build_openai_trace_kwargs, get_openai_class
from backend.tools.prompts.news import NEWS_SUMMARY_PROMPT_TEMPLATE
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from tqdm.auto import tqdm

logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH if ENV_PATH.exists() else None)
load_backend_env()

DB_URL_ENV_NAME = "DATABASE_URL"
DB_HOST_ENV_NAME = "POSTGRES_HOST"
DB_PORT_ENV_NAME = "POSTGRES_PORT"
DB_USER_ENV_NAME = "POSTGRES_USER"
DB_PASSWORD_ENV_NAME = "POSTGRES_PASSWORD"
DB_NAME_ENV_NAME = "POSTGRES_DB"

SME_LIST_TABLE_NAME = "sme_list"
DAUM_NEWS_TABLE_NAME = "daum_news_articles"

DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_MAX_ARTICLES = 5
DEFAULT_PAGE_SIZE = 20
DEFAULT_REQUEST_TIMEOUT = 10
DEFAULT_LIST_DELAY_SEC = 0.4
DEFAULT_CONTENT_DELAY_SEC = 1.0
DEFAULT_SUMMARY_MODEL = get_model_name()
DEFAULT_SUMMARIZE = True

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


class Base(DeclarativeBase):
    """뉴스 적재용 ORM 베이스."""


class DaumNewsArticle(Base):
    """수집한 다음 뉴스 적재 테이블."""

    __tablename__ = DAUM_NEWS_TABLE_NAME
    __table_args__ = (
        UniqueConstraint("stock_code", "url", name="uq_daum_news_stock_code_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    corp_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    news_title: Mapped[str] = mapped_column(Text, nullable=False)
    press_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )


@dataclass(frozen=True, slots=True)
class SMECompany:
    stock_code: str
    corp_name: str


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def resolve_database_url() -> str:
    database_url = os.getenv(DB_URL_ENV_NAME, "").strip()
    if database_url:
        return database_url

    host = os.getenv(DB_HOST_ENV_NAME, "localhost").strip()
    port = os.getenv(DB_PORT_ENV_NAME, "5432").strip()
    user = os.getenv(DB_USER_ENV_NAME, "").strip()
    password = os.getenv(DB_PASSWORD_ENV_NAME, "").strip()
    database = os.getenv(DB_NAME_ENV_NAME, "").strip()

    if not user or not password or not database:
        raise ValueError(
            "PostgreSQL 연결 정보를 찾지 못했습니다. .env 파일에 "
            "DATABASE_URL 또는 POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB "
            "값을 설정해주세요."
        )

    quoted_password = quote_plus(password)
    return f"postgresql+psycopg2://{user}:{quoted_password}@{host}:{port}/{database}"


def create_db_engine(database_url: str | None = None):
    return create_engine(database_url or resolve_database_url())


def create_tables(engine) -> None:
    Base.metadata.create_all(engine, tables=[DaumNewsArticle.__table__])


def build_daum_headers(stock_code: str) -> dict[str, str]:
    return {
        **DEFAULT_HEADERS,
        "Referer": f"https://finance.daum.net/quotes/{stock_code}",
    }


def _normalize_stock_code(stock_code: str) -> str:
    stripped = stock_code.strip()
    if not stripped:
        return ""
    return stripped if stripped.startswith("A") else f"A{stripped}"


def _parse_created_at(value: str) -> datetime | None:
    if not value:
        return None

    normalized = value.strip().replace("T", " ")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized[:19], fmt)
        except ValueError:
            continue
    return None


def _build_article_url(item: dict[str, Any]) -> str:
    content_url = (item.get("contentUrl") or "").strip()
    if content_url:
        return content_url

    raw_url = (item.get("url") or "").strip()
    if raw_url:
        return raw_url

    news_id = item.get("newsId")
    if news_id:
        return f"https://v.daum.net/v/{news_id}"

    return ""


def load_sme_companies(session: Session, limit: int | None = None) -> list[SMECompany]:
    query = (
        f"SELECT stock_code, corp_name FROM {SME_LIST_TABLE_NAME} "
        "WHERE stock_code IS NOT NULL AND TRIM(stock_code) <> '' "
        "AND corp_name IS NOT NULL AND TRIM(corp_name) <> '' "
        "ORDER BY corp_name ASC"
    )
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    rows = session.execute(text(query)).all()
    companies = [
        SMECompany(stock_code=str(stock_code).strip(), corp_name=str(corp_name).strip())
        for stock_code, corp_name in rows
        if str(stock_code).strip() and str(corp_name).strip()
    ]
    logger.info("sme_company_load_finished company_count=%s", len(companies))
    return companies


def filter_sme_companies(
    companies: list[SMECompany],
    *,
    company_name: str | None = None,
    corp_name: str | None = None,
    stock_code: str | None = None,
) -> list[SMECompany]:
    target_names = {
        _normalize_text(company_name),
        _normalize_text(corp_name),
    }
    target_names.discard("")
    normalized_stock_code = _normalize_stock_code(_normalize_text(stock_code))

    if not target_names and not normalized_stock_code:
        return companies

    filtered_companies = [
        company
        for company in companies
        if (
            company.corp_name in target_names
            or _normalize_stock_code(company.stock_code) == normalized_stock_code
        )
    ]
    logger.info(
        (
            "sme_company_filter_finished requested_names=%s "
            "requested_stock_code=%s company_count=%s"
        ),
        sorted(target_names),
        normalized_stock_code,
        len(filtered_companies),
    )
    return filtered_companies


def extract_daum_news_list(
    stock_code: str,
    headers: dict[str, str] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_articles: int = DEFAULT_MAX_ARTICLES,
    per_page: int = DEFAULT_PAGE_SIZE,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    request_delay_sec: float = DEFAULT_LIST_DELAY_SEC,
) -> list[dict[str, Any]]:
    normalized_stock_code = _normalize_stock_code(stock_code)
    if not normalized_stock_code:
        raise ValueError("stock_code는 비어 있을 수 없습니다.")

    request_headers = headers or build_daum_headers(normalized_stock_code)
    cutoff_date = datetime.now() - timedelta(days=lookback_days)
    list_news_data: list[dict[str, Any]] = []
    page = 1
    is_continuable = True

    logger.info(
        (
            "daum_news_list_collection_started stock_code=%s "
            "lookback_days=%s max_articles=%s per_page=%s"
        ),
        normalized_stock_code,
        lookback_days,
        max_articles,
        per_page,
    )

    while is_continuable:
        api_url = (
            "https://finance.daum.net/content/news"
            f"?page={page}&perPage={per_page}&category=economy"
            f"&searchType=all&keyword={normalized_stock_code}&pagination=true"
        )

        try:
            response = requests.get(
                api_url,
                headers=request_headers,
                timeout=request_timeout,
            )

            if response.status_code != 200:
                logger.warning(
                    (
                        "daum_news_list_request_failed stock_code=%s "
                        "page=%s status_code=%s"
                    ),
                    normalized_stock_code,
                    page,
                    response.status_code,
                )
                break

            news_items = response.json().get("data", [])
            if not news_items:
                logger.info(
                    "daum_news_list_empty_page stock_code=%s page=%s",
                    normalized_stock_code,
                    page,
                )
                break

            logger.info(
                "daum_news_list_page_parsed stock_code=%s page=%s item_count=%s",
                normalized_stock_code,
                page,
                len(news_items),
            )

            for item in news_items:
                created_at = (item.get("createdAt") or "").strip()
                news_date = _parse_created_at(created_at)
                if news_date is None:
                    logger.warning(
                        (
                            "daum_news_list_invalid_date stock_code=%s "
                            "page=%s created_at=%s"
                        ),
                        normalized_stock_code,
                        page,
                        created_at,
                    )
                    continue

                if news_date < cutoff_date:
                    logger.info(
                        (
                            "daum_news_list_cutoff_reached stock_code=%s "
                            "page=%s created_at=%s cutoff=%s"
                        ),
                        normalized_stock_code,
                        page,
                        created_at,
                        cutoff_date.isoformat(),
                    )
                    is_continuable = False
                    break

                list_news_data.append(
                    {
                        "title": (item.get("title") or "").strip(),
                        "description": (item.get("summary") or "").strip(),
                        "press": (item.get("cpName") or "").strip(),
                        "date": created_at,
                        "published_at": news_date,
                        "url": _build_article_url(item),
                    }
                )
                if len(list_news_data) >= max_articles:
                    logger.info(
                        (
                            "daum_news_list_article_limit_reached "
                            "stock_code=%s max_articles=%s"
                        ),
                        normalized_stock_code,
                        max_articles,
                    )
                    is_continuable = False
                    break

            if is_continuable:
                time.sleep(request_delay_sec)
                page += 1

        except Exception:  # noqa: BLE001
            logger.exception(
                "daum_news_list_collection_failed stock_code=%s page=%s",
                normalized_stock_code,
                page,
            )
            break

    logger.info(
        "daum_news_list_collection_finished stock_code=%s article_count=%s",
        normalized_stock_code,
        len(list_news_data),
    )
    return list_news_data


def extract_daum_news_contents(
    news_list: list[dict[str, Any]],
    headers: dict[str, str] | None = None,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    request_delay_sec: float = DEFAULT_CONTENT_DELAY_SEC,
    show_progress: bool = True,
    progress_desc: str = "뉴스 데이터 보완 중",
    progress_position: int = 1,
    leave_progress: bool = False,
) -> list[dict[str, Any]]:
    if not news_list:
        logger.info("daum_news_content_collection_skipped reason=empty_news_list")
        return news_list

    request_headers = headers or DEFAULT_HEADERS
    logger.info("daum_news_content_collection_started article_count=%s", len(news_list))

    iterable = (
        tqdm(
            news_list,
            desc=progress_desc,
            position=progress_position,
            leave=leave_progress,
        )
        if show_progress
        else news_list
    )

    for news in iterable:
        url = (news.get("url") or "").strip()
        if not url or "v.daum.net" not in url:
            news["content"] = "본문을 가져올 수 없는 링크입니다."
            logger.warning("daum_news_content_invalid_url url=%s", url)
            continue

        try:
            response = requests.get(
                url,
                headers=request_headers,
                timeout=request_timeout,
            )

            if response.status_code != 200:
                news["content"] = f"페이지 접근 실패 (상태코드: {response.status_code})"
                logger.warning(
                    "daum_news_content_request_failed url=%s status_code=%s",
                    url,
                    response.status_code,
                )
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            if not (news.get("press") or "").strip():
                date_p = soup.find("p", class_="date")
                if date_p and "·" in date_p.text:
                    news["press"] = date_p.text.split("·")[0].strip()
                else:
                    meta_press = soup.find("meta", property="og:article:author")
                    news["press"] = (
                        meta_press.get("content", "").strip()
                        if meta_press
                        else "언론사 확인 필요"
                    )

            article_view = soup.find("div", class_="article_view")
            if article_view:
                paragraphs = article_view.find_all("p")
                news["content"] = "\n".join(
                    p.text.strip() for p in paragraphs if p.text.strip()
                )
            else:
                dm_content = soup.find("section", id="dm-content")
                if dm_content:
                    news["content"] = dm_content.get_text("\n", strip=True)
                else:
                    news["content"] = "본문 영역을 찾을 수 없습니다."
                    logger.warning("daum_news_content_missing_body url=%s", url)

        except Exception:  # noqa: BLE001
            news["content"] = "본문 수집 중 에러 발생"
            logger.exception("daum_news_content_collection_failed url=%s", url)

        time.sleep(request_delay_sec)

    logger.info(
        "daum_news_content_collection_finished article_count=%s",
        len(news_list),
    )
    return news_list


def get_openai_client() -> Any:
    client_class = get_openai_class()
    return client_class(**build_llm_client_kwargs())


def get_llm_summary(
    text: str,
    client: Any | None = None,
    model_name: str = DEFAULT_SUMMARY_MODEL,
    *,
    corp_name: str | None = None,
    request_id: str | None = None,
) -> tuple[str, float]:
    if not text or len(text.strip()) < 50:
        return "본문이 너무 짧습니다.", 0.0

    summary_client = client or get_openai_client()
    prompt = NEWS_SUMMARY_PROMPT_TEMPLATE.format(text=text)

    start_time = time.time()
    try:
        response = summary_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            **build_openai_trace_kwargs(
                name="news.summary",
                session_id=request_id,
                tags=["news_collector", "summary"],
                metadata={
                    "agent_name": "news_collector",
                    "company_name": corp_name,
                    "input_length": len(text),
                },
            ),
        )
        summary_result = response.choices[0].message.content.strip()
        latency = time.time() - start_time
        logger.info(
            "daum_news_summary_completed model=%s input_length=%s latency_sec=%.2f",
            model_name,
            len(text),
            latency,
        )
        return summary_result, latency
    except Exception:  # noqa: BLE001
        logger.exception(
            "daum_news_summary_failed model=%s input_length=%s",
            model_name,
            len(text),
        )
        return "요약 실패", 0.0


def build_article_payload(
    *,
    stock_code: str,
    corp_name: str,
    news: dict[str, Any],
    summarize: bool = DEFAULT_SUMMARIZE,
    summary_client: Any | None = None,
    model_name: str = DEFAULT_SUMMARY_MODEL,
    request_id: str | None = None,
) -> dict[str, Any]:
    article_content = (news.get("content") or "").strip()
    stored_content = article_content
    content_type = "full_text"

    if summarize:
        summary_text, _ = get_llm_summary(
            article_content,
            client=summary_client,
            model_name=model_name,
            corp_name=corp_name,
            request_id=request_id,
        )
        stored_content = summary_text
        content_type = "summary"

    return {
        "stock_code": stock_code.strip(),
        "corp_name": corp_name.strip(),
        "news_title": (news.get("title") or "").strip(),
        "press_name": (news.get("press") or "").strip(),
        "published_at": news.get("published_at")
        or _parse_created_at(news.get("date", "")),
        "url": (news.get("url") or "").strip(),
        "content": stored_content,
        "content_type": content_type,
    }


def build_risk_event_news_item(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": article["news_title"],
        "content": article["content"],
        "published_at": article["published_at"].isoformat()
        if article.get("published_at")
        else None,
        "url": article["url"],
        "press": article.get("press_name", ""),
        "corp_name": article.get("corp_name", ""),
        "stock_code": article.get("stock_code", ""),
        "content_type": article.get("content_type", ""),
    }


def upsert_news_articles(
    session: Session,
    articles: list[dict[str, Any]],
) -> dict[str, int]:
    inserted_count = 0
    updated_count = 0

    for article in articles:
        existing = session.execute(
            select(DaumNewsArticle).where(
                DaumNewsArticle.stock_code == article["stock_code"],
                DaumNewsArticle.url == article["url"],
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(DaumNewsArticle(**article))
            inserted_count += 1
            continue

        existing.corp_name = article["corp_name"]
        existing.news_title = article["news_title"]
        existing.press_name = article["press_name"]
        existing.published_at = article["published_at"]
        existing.content = article["content"]
        existing.content_type = article["content_type"]
        updated_count += 1

    session.commit()
    logger.info(
        "daum_news_db_upsert_finished inserted_count=%s updated_count=%s",
        inserted_count,
        updated_count,
    )
    return {"inserted_count": inserted_count, "updated_count": updated_count}


def execute_news_pipeline(
    *,
    database_url: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_articles: int = DEFAULT_MAX_ARTICLES,
    summarize: bool = DEFAULT_SUMMARIZE,
    model_name: str = DEFAULT_SUMMARY_MODEL,
    company_limit: int | None = None,
    show_progress: bool = True,
    company_name: str | None = None,
    corp_name: str | None = None,
    stock_code: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    engine = create_db_engine(database_url)
    create_tables(engine)

    stats = {
        "company_count": 0,
        "article_count": 0,
        "article_limit": max_articles,
        "inserted_count": 0,
        "updated_count": 0,
        "target_company_count": 0,
        "collected_news_data": [],
        "status": "success",
    }
    summary_client = get_openai_client() if summarize else None

    with Session(engine) as session:
        companies = load_sme_companies(session, limit=company_limit)
        stats["company_count"] = len(companies)
        companies = filter_sme_companies(
            companies,
            company_name=company_name,
            corp_name=corp_name,
            stock_code=stock_code,
        )
        stats["target_company_count"] = len(companies)

        iterable = (
            tqdm(companies, desc="SME 뉴스 수집 중", position=0)
            if show_progress
            else companies
        )
        for company_index, company in enumerate(iterable, start=1):
            logger.info("%s", "=" * 80)
            logger.info(
                (
                    "daum_news_company_collection_started company_index=%s "
                    "total_companies=%s stock_code=%s corp_name=%s"
                ),
                company_index,
                len(companies),
                company.stock_code,
                company.corp_name,
            )
            logger.info("%s", "-" * 80)

            news_list = extract_daum_news_list(
                company.stock_code,
                lookback_days=lookback_days,
                max_articles=max_articles,
            )
            news_list = extract_daum_news_contents(
                news_list,
                show_progress=show_progress,
                progress_desc=(
                    f"[{company_index}/{len(companies)}] "
                    f"{company.corp_name} 기사 수집 중"
                ),
                progress_position=1,
                leave_progress=False,
            )

            articles = [
                build_article_payload(
                    stock_code=company.stock_code,
                    corp_name=company.corp_name,
                    news=news,
                    summarize=summarize,
                    summary_client=summary_client,
                    model_name=model_name,
                    request_id=request_id,
                )
                for news in news_list
                if (news.get("title") or "").strip() and (news.get("url") or "").strip()
            ]

            result = upsert_news_articles(session, articles)
            stats["collected_news_data"].extend(
                build_risk_event_news_item(article) for article in articles
            )
            stats["article_count"] += len(articles)
            stats["inserted_count"] += result["inserted_count"]
            stats["updated_count"] += result["updated_count"]

            logger.info(
                (
                    "daum_news_company_collection_finished "
                    "company_index=%s total_companies=%s "
                    "stock_code=%s corp_name=%s article_count=%s"
                ),
                company_index,
                len(companies),
                company.stock_code,
                company.corp_name,
                len(articles),
            )
            logger.info("%s", "=" * 80)

    engine.dispose()
    logger.info("daum_news_pipeline_finished stats=%s", stats)
    return stats
