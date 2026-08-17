"""Markdown rapor üretimi + Telegram 4096 karakter limitine göre mesaj bölme."""
from __future__ import annotations

from telegram.helpers import escape_markdown

from app.domain.models import CandidateProfile, EvaluationResult, MultiAnalysisResponse

TELEGRAM_MAX_LEN = 4000  # 4096 sınırının altında güvenli pay


def _bulleted(items: list[str]) -> list[str]:
    if not items:
        return ["- (belirtilmedi)"]
    return [f"- {escape_markdown(item, version=1)}" for item in items]


def format_single_analysis(profile: CandidateProfile, evaluation: EvaluationResult) -> str:
    name = escape_markdown(profile.candidateName or "Aday", version=1)
    lines = [f"*{name} — Analiz Raporu*", "", "*Kriter Skorları*"]
    for score in evaluation.scores:
        label = escape_markdown(score.criterionLabel, version=1)
        reason = escape_markdown(score.reason, version=1)
        lines.append(f"- {label}: {score.score}/100 — {reason}")

    lines += ["", "*Güçlü Yönler*", *_bulleted(evaluation.strengths)]
    lines += ["", "*Zayıf Yönler*", *_bulleted(evaluation.weaknesses)]
    lines += ["", "*Gelişim Tavsiyeleri*", *_bulleted(evaluation.recommendations)]
    summary = escape_markdown(evaluation.hrEvaluation, version=1)
    lines += ["", f"*Genel Değerlendirme:* {summary}"]
    return "\n".join(lines)


def format_multi_analysis_json(response: MultiAnalysisResponse) -> str:
    return response.model_dump_json(indent=2)


def chunk_message(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]
