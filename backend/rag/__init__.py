__all__ = [
    "ingest_industry_docs",
    "retrieve_industry_methodology",
]


def __getattr__(name: str):
    if name == "ingest_industry_docs":
        from backend.rag.ingest_industry_docs import ingest_industry_docs

        return ingest_industry_docs
    if name == "retrieve_industry_methodology":
        from backend.rag.retriever import retrieve_industry_methodology

        return retrieve_industry_methodology
    raise AttributeError(name)
