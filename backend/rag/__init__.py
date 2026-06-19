__all__ = [
    "build_industry_agent_ragas_eval_rows",
    "build_industry_ragas_eval_rows",
    "ingest_industry_docs",
    "load_industry_agent_ragas_eval_cases",
    "load_industry_ragas_eval_cases",
    "run_industry_ragas_evaluation",
    "retrieve_industry_methodology",
    "write_industry_ragas_report",
]


def __getattr__(name: str):
    if name == "build_industry_agent_ragas_eval_rows":
        from backend.rag.evaluation import build_industry_agent_ragas_eval_rows

        return build_industry_agent_ragas_eval_rows
    if name == "build_industry_ragas_eval_rows":
        from backend.rag.evaluation import build_industry_ragas_eval_rows

        return build_industry_ragas_eval_rows
    if name == "ingest_industry_docs":
        from backend.rag.ingest_industry_docs import ingest_industry_docs

        return ingest_industry_docs
    if name == "load_industry_agent_ragas_eval_cases":
        from backend.rag.evaluation import load_industry_agent_ragas_eval_cases

        return load_industry_agent_ragas_eval_cases
    if name == "load_industry_ragas_eval_cases":
        from backend.rag.evaluation import load_industry_ragas_eval_cases

        return load_industry_ragas_eval_cases
    if name == "run_industry_ragas_evaluation":
        from backend.rag.evaluation import run_industry_ragas_evaluation

        return run_industry_ragas_evaluation
    if name == "retrieve_industry_methodology":
        from backend.rag.retriever import retrieve_industry_methodology

        return retrieve_industry_methodology
    if name == "write_industry_ragas_report":
        from backend.rag.evaluation import write_industry_ragas_report

        return write_industry_ragas_report
    raise AttributeError(name)
