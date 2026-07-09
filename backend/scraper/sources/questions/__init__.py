"""Question-bank sources registry (PHASE4.md step 1)."""

from backend.scraper.sources._base import Source
from backend.scraper.sources.questions.github_questions import FaqguruQuestions, GitHubQuestions
from backend.scraper.sources.questions.hn import HNInterviews

SOURCES: dict[str, Source] = {
    "hn-interviews": HNInterviews(),
    "github-questions": GitHubQuestions(),
    "faqguru-questions": FaqguruQuestions(),
}
