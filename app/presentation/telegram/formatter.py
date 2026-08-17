"""Markdown rapor üretimi + Telegram 4096 karakter limitine göre mesaj bölme."""
from __future__ import annotations

from app.domain.models import CandidateProfile, EvaluationResult, MultiAnalysisResponse

TELEGRAM_MAX_LEN = 4000  # 4096 sınırının altında güvenli pay


def _bulleted(items: list[str]) -> list[str]:
    if not items:
        return ["- (belirtilmedi)"]
    return [f"- {item}" for item in items]


def format_single_analysis(profile: CandidateProfile, evaluation: EvaluationResult) -> str:
    name = profile.candidateName or "Aday"
    lines = [f"*{name} — Analiz Raporu*", "", "*Kriter Skorları*"]
    for score in evaluation.scores:
        lines.append(f"- {score.criterionLabel}: {score.score}/100 — {score.reason}")

    lines += ["", "*Güçlü Yönler*", *_bulleted(evaluation.strengths)]
    lines += ["", "*Zayıf Yönler*", *_bulleted(evaluation.weaknesses)]
    lines += ["", "*Gelişim Tavsiyeleri*", *_bulleted(evaluation.recommendations)]
    lines += ["", f"*Genel Değerlendirme:* {evaluation.hrEvaluation}"]
    return "\n".join(lines)


def format_multi_analysis_json(response: MultiAnalysisResponse) -> str:
    return "```\n" + response.model_dump_json(indent=2) + "\n```"


def chunk_message(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]
