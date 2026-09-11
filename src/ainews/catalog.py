"""Topic taxonomy, keyword rules, and the seed source list.

Two source kinds, and the distinction is what keeps this cheap:

  topical  - covers one beat. Every article inherits the source's topics, so no
             per-article analysis is needed at all.
  broad    - covers all of AI. Articles must be matched to topics individually.

Only broad sources pay classification cost. Adding a topical source is free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- topics

@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    description: str


TOPICS: list[Topic] = [
    Topic("llms", "LLMs & Frontier Models", "Model releases, capabilities, benchmarks and lab research."),
    Topic("agents", "Agents & Tooling", "Autonomous agents, tool use, browsers and orchestration."),
    Topic("coding", "AI for Coding", "Coding assistants, dev workflow and open-source tooling."),
    Topic("chips", "Chips & Infrastructure", "Accelerators, datacenters, supply chain and serving cost."),
    Topic("power", "Power & Energy", "Electricity demand, grid constraints and datacenter siting."),
    Topic("robotics", "Robotics & Embodied AI", "Physical systems, manipulation and autonomy."),
    Topic("safety", "Safety & Alignment", "Alignment research, evaluations, model behaviour and risk."),
    Topic("policy", "Policy & Regulation", "Legislation, enforcement, courts and standards."),
    Topic("business", "Business & Funding", "Funding rounds, earnings, market structure and adoption."),
    Topic("applied", "Applied & Vertical AI", "AI in health, finance, legal, education and industry."),
]

# ------------------------------------------------------------------- keyword rules
# Applied to broad-source articles only, against title + publisher RSS summary.
# A single strong hit qualifies; two weak hits also qualify at lower confidence.

@dataclass(frozen=True)
class Rule:
    strong: tuple[str, ...] = ()
    weak: tuple[str, ...] = ()


KEYWORDS: dict[str, Rule] = {
    "llms": Rule(
        strong=("large language model", "frontier model", "gpt-5", "gpt-6", "claude ", "gemini",
                "llama ", "mistral", "deepseek", "qwen", "foundation model", "model card"),
        weak=("benchmark", "context window", "fine-tun", "parameters", "reasoning model", "multimodal"),
    ),
    "agents": Rule(
        strong=("ai agent", "agentic", "autonomous agent", "tool use", "computer use",
                "mcp", "model context protocol", "browser agent"),
        weak=("workflow", "orchestrat", "assistant", "automation"),
    ),
    "coding": Rule(
        strong=("copilot", "cursor", "code generation", "coding assistant", "swe-bench",
                "vibe coding", "pull request", "developer tool"),
        weak=("open source", "repository", "ide", "programming", "software engineer"),
    ),
    "chips": Rule(
        strong=("gpu", "tpu", "nvidia", "blackwell", "hbm", "tsmc", "accelerator",
                "semiconductor", "wafer", "inference cost", "datacenter"),
        weak=("cluster", "supply chain", "export control", "chip", "compute"),
    ),
    "power": Rule(
        strong=("electricity", "power grid", "megawatt", "gigawatt", "nuclear",
                "energy demand", "utility", "transmission", "power purchase"),
        weak=("cooling", "emissions", "carbon", "siting", "substation"),
    ),
    "robotics": Rule(
        strong=("robot", "humanoid", "embodied", "manipulation", "autonomous vehicle",
                "drone", "warehouse automation"),
        weak=("actuator", "sensor", "locomotion", "teleoperation"),
    ),
    "safety": Rule(
        strong=("ai safety", "alignment", "red team", "jailbreak", "interpretability",
                "model welfare", "existential risk", "guardrail"),
        weak=("evaluation", "hallucinat", "misuse", "bias", "oversight"),
    ),
    "policy": Rule(
        strong=("regulation", "legislation", "lawsuit", "attorney general", "ftc", "eu ai act",
                "executive order", "copyright", "antitrust", "compliance", "court"),
        weak=("policy", "senate", "congress", "state law", "privacy", "enforcement"),
    ),
    "business": Rule(
        strong=("funding round", "series a", "series b", "series c", "valuation", "ipo",
                "acquisition", "earnings", "raises $", "venture capital"),
        weak=("revenue", "startup", "investor", "market share", "layoff"),
    ),
    "applied": Rule(
        strong=("healthcare", "clinical", "drug discovery", "fintech", "legal tech",
                "education", "manufacturing", "agriculture", "radiology"),
        weak=("deployment", "enterprise", "industry", "adoption", "pilot"),
    ),
}

_COMPILED: dict[str, tuple[list[re.Pattern], list[re.Pattern]]] = {}


def _compile() -> None:
    if _COMPILED:
        return
    for slug, rule in KEYWORDS.items():
        def pats(terms: tuple[str, ...]) -> list[re.Pattern]:
            out = []
            for t in terms:
                # Trailing space in a term means "prefix, then a boundary".
                body = re.escape(t.strip())
                out.append(re.compile(rf"(?<!\w){body}", re.IGNORECASE))
            return out
        _COMPILED[slug] = (pats(rule.strong), pats(rule.weak))


def classify(title: str, summary: str | None) -> list[tuple[str, float]]:
    """Return [(topic_slug, confidence)] for a broad-source article."""
    _compile()
    text = f"{title} {summary or ''}"
    hits: list[tuple[str, float]] = []
    for slug, (strong, weak) in _COMPILED.items():
        s = sum(1 for p in strong if p.search(text))
        w = sum(1 for p in weak if p.search(text))
        if s >= 1:
            hits.append((slug, min(1.0, 0.70 + 0.10 * (s - 1) + 0.05 * w)))
        elif w >= 2:
            hits.append((slug, 0.50))
    # Keep the three best so a single article does not blanket the taxonomy.
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits[:3]


# ------------------------------------------------------------------------ sources
# Every feed URL below was fetched and parsed successfully on 2026-09-10.

@dataclass(frozen=True)
class Source:
    slug: str
    name: str
    homepage_url: str
    feed_url: str
    kind: str            # 'broad' | 'topical'
    quality_tier: int    # 1 best, 3 lowest — feeds ranking
    blurb: str
    topics: tuple[str, ...] = field(default=())


SOURCES: list[Source] = [
    # ---- broad: classified per article
    Source("techcrunch-ai", "TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/",
           "https://techcrunch.com/category/artificial-intelligence/feed/", "broad", 2,
           "High-volume industry and funding coverage."),
    Source("verge-ai", "The Verge AI", "https://www.theverge.com/ai-artificial-intelligence",
           "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "broad", 2,
           "Consumer-facing AI news and product launches."),
    Source("mit-tech-review", "MIT Technology Review", "https://www.technologyreview.com/",
           "https://www.technologyreview.com/feed/", "broad", 1,
           "Reported features with more depth than the news cycle."),
    Source("ars-technica", "Ars Technica", "https://arstechnica.com/",
           "https://feeds.arstechnica.com/arstechnica/index", "broad", 2,
           "Technical reporting; strong on infrastructure and security."),
    Source("simon-willison", "Simon Willison", "https://simonwillison.net/",
           "https://simonwillison.net/atom/everything/", "broad", 1,
           "Practitioner notes on models and tooling, near-daily."),
    Source("import-ai", "Import AI (Jack Clark)", "https://jack-clark.net/",
           "https://jack-clark.net/feed/", "broad", 1,
           "Weekly policy and research judgement from a former lab policy lead."),
    Source("register-ai", "The Register — AI/ML", "https://www.theregister.com/software/ai_ml/",
           "https://www.theregister.com/software/ai_ml/headlines.atom", "broad", 3,
           "Sceptical enterprise coverage; useful counterweight."),
    Source("wired-ai", "WIRED AI", "https://www.wired.com/tag/artificial-intelligence/",
           "https://www.wired.com/feed/tag/ai/latest/rss", "broad", 2,
           "Culture, policy and business angles on AI."),

    # ---- topical: articles inherit the source's topics
    Source("openai-news", "OpenAI News", "https://openai.com/news/",
           "https://openai.com/news/rss.xml", "topical", 1,
           "Primary source for OpenAI releases and research.", ("llms",)),
    Source("deepmind-blog", "Google DeepMind", "https://deepmind.google/discover/blog/",
           "https://deepmind.google/blog/rss.xml", "topical", 1,
           "Primary source for DeepMind research.", ("llms",)),
    Source("google-ai-blog", "Google AI", "https://blog.google/technology/ai/",
           "https://blog.google/technology/ai/rss/", "topical", 2,
           "Google's own AI product and research announcements.", ("llms",)),
    Source("arxiv-cs-ai", "arXiv cs.AI", "https://arxiv.org/list/cs.AI/recent",
           "http://export.arxiv.org/rss/cs.AI", "topical", 3,
           "Raw preprint firehose. Deliberately ranked last.", ("llms",)),
    Source("alignment-forum", "Alignment Forum", "https://www.alignmentforum.org/",
           "https://www.alignmentforum.org/feed.xml", "topical", 2,
           "Technical alignment and interpretability discussion.", ("safety",)),
    Source("semianalysis", "SemiAnalysis", "https://semianalysis.com/",
           "https://semianalysis.com/feed/", "topical", 1,
           "Deep compute supply-chain and datacenter economics.", ("chips", "power")),
    Source("nvidia-blog", "NVIDIA Blog", "https://blogs.nvidia.com/",
           "https://blogs.nvidia.com/feed/", "topical", 3,
           "Vendor blog — treat as marketing with useful specifics.", ("chips", "robotics")),
    Source("ieee-robotics", "IEEE Spectrum — Robotics", "https://spectrum.ieee.org/topic/robotics/",
           "https://spectrum.ieee.org/feeds/topic/robotics.rss", "topical", 1,
           "The best general robotics coverage available.", ("robotics",)),
    Source("huggingface-blog", "Hugging Face Blog", "https://huggingface.co/blog",
           "https://huggingface.co/blog/feed.xml", "topical", 2,
           "Open-source models and practical tooling.", ("coding", "llms")),
    Source("github-blog-ai", "GitHub Blog — AI & ML", "https://github.blog/ai-and-ml/",
           "https://github.blog/ai-and-ml/feed/", "topical", 2,
           "Developer workflow and Copilot changes.", ("coding",)),
    Source("ieee-energy", "IEEE Spectrum — Energy", "https://spectrum.ieee.org/topic/energy/",
           "https://spectrum.ieee.org/feeds/topic/energy.rss", "topical", 2,
           "Grid and generation engineering.", ("power",)),
    Source("utility-dive", "Utility Dive", "https://www.utilitydive.com/",
           "https://www.utilitydive.com/feeds/news/", "topical", 2,
           "Utility-side view of datacenter load growth.", ("power",)),
    Source("canary-media", "Canary Media", "https://www.canarymedia.com/",
           "https://www.canarymedia.com/feed", "topical", 3,
           "Clean energy reporting; datacenter demand coverage.", ("power",)),
    Source("crunchbase-news", "Crunchbase News", "https://news.crunchbase.com/",
           "https://news.crunchbase.com/feed/", "topical", 2,
           "Funding rounds and venture activity.", ("business",)),
    Source("tc-venture", "TechCrunch Venture", "https://techcrunch.com/category/venture/",
           "https://techcrunch.com/category/venture/feed/", "topical", 2,
           "Venture financing news.", ("business",)),
]
