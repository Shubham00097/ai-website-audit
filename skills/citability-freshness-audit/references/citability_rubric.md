# Citability Scoring Rubric

## Overview

Each content block (paragraph ≥20 words) is scored on five dimensions. Scores
aggregate to a 0–100 value per block. The page receives the average score across
all qualifying blocks plus a bonus for having many scoreable blocks.

## Dimensions

| Dimension | Weight | What it measures |
|---|---|---|
| Answer block quality | 30 pts | Does the paragraph start with a direct, quotable answer to an implied question? |
| Self-containment | 25 pts | Does the passage still make sense if extracted and shown without the surrounding page? |
| Structural readability | 20 pts | Lists, tables, scannable formatting present near this content block |
| Statistical density | 15 pts | Specific numbers, years, percentages, or named entities present |
| Uniqueness | 10 pts | Original data or analysis rather than restated consensus or marketing boilerplate |

## Score Bands

| Score | Band | Interpretation |
|---|---|---|
| 80–100 | **Excellent** | Highly extractable and quotable by AI systems |
| 60–79 | **Good** | Extractable with minor improvements |
| 40–59 | **Needs Work** | Partially extractable; key dimensions missing |
| 0–39 | **Poor** | Unlikely to be quoted; significant rewrite needed |

## Heuristics per Dimension

### Answer Block Quality (30 pts)
- **30 pts**: First sentence directly answers "what", "why", "how", or "when"
- **15 pts**: First two sentences contain an implied answer
- **0 pts**: Paragraph is promotional, vague, or starts with "we" / "our"

### Self-Containment (25 pts)
- **25 pts**: No pronouns or anaphora requiring surrounding context ("it", "this", "as mentioned")
- **12 pts**: One or two context-dependent references
- **0 pts**: Paragraph requires the full page to be understood

### Structural Readability (20 pts)
- **20 pts**: Content is in a list or table, or immediately preceded by a descriptive heading
- **10 pts**: Clear paragraph breaks and short sentences
- **0 pts**: Dense wall of text with no structure

### Statistical Density (15 pts)
- **15 pts**: Contains ≥2 specific numbers, dates, or named entities
- **8 pts**: Contains 1 number, date, or named entity
- **0 pts**: Purely qualitative, no verifiable specifics

### Uniqueness (10 pts)
- **10 pts**: Contains original research, proprietary data, or first-hand account
- **5 pts**: Contains curated information with attribution
- **0 pts**: Generic, widely-repeated information without attribution

## Thresholds for Findings

- Page average score < 40 → **medium** finding (poor AI citability)
- Zero qualifying content blocks found → **medium** finding
- All blocks are purely promotional → **medium** finding
