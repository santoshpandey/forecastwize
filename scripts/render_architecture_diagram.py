"""Render the ForecastWize architecture diagram as PNG. Display only; no forecast math."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 2880, 1720
BG = (244, 244, 242)
SURFACE = (255, 255, 255)
INK = (27, 27, 27)
MUTED = (94, 94, 94)
LINE = (214, 212, 206)
AGENT_FILL = (232, 238, 244)
AGENT_STROKE = (31, 78, 121)
DET_FILL = (238, 246, 241)
DET_STROKE = (27, 94, 59)
GATE_FILL = (251, 246, 234)
GATE_STROKE = (122, 84, 0)
CHALLENGE = (139, 30, 30)
LAYER = (250, 250, 248)
OUTPUT_FILL = (247, 247, 245)
ACCENT = (31, 78, 121)

ROOT = Path(__file__).resolve().parents[1]
OUT_PNG = ROOT / "docs" / "forecastwize-architecture.png"
FONT_REG = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")
KIND = {
    "agent": (AGENT_FILL, AGENT_STROKE),
    "det": (DET_FILL, DET_STROKE),
    "gate": (GATE_FILL, GATE_STROKE),
    "plain": (SURFACE, LINE),
    "output": (OUTPUT_FILL, (180, 178, 172)),
}


def _font_path(bold: bool) -> Path:
    return FONT_BOLD if bold else FONT_REG


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_font_path(bold)), size)


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill,
    outline,
    width: int = 2,
    radius: int = 10,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill=INK,
) -> None:
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x - tw / 2, y - th / 2), text, font=fnt, fill=fill)


def wrap_center(
    draw: ImageDraw.ImageDraw,
    cx: float,
    y: float,
    text: str,
    fnt: ImageFont.FreeTypeFont,
    max_width: int,
    fill=INK,
    line_gap: int = 3,
) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=fnt)
        th = bbox[3] - bbox[1]
        center_text(draw, (cx, y + i * (th + line_gap)), line, fnt, fill)


def arrow_down(draw: ImageDraw.ImageDraw, x: int, y0: int, y1: int, color=INK) -> None:
    draw.line((x, y0, x, y1 - 9), fill=color, width=3)
    draw.polygon([(x, y1), (x - 7, y1 - 12), (x + 7, y1 - 12)], fill=color)


def arrow_right(draw: ImageDraw.ImageDraw, x0: int, y: int, x1: int, color=INK) -> None:
    draw.line((x0, y, x1 - 9, y), fill=color, width=3)
    draw.polygon([(x1, y), (x1 - 12, y - 7), (x1 - 12, y + 7)], fill=color)


def arrow_up(draw: ImageDraw.ImageDraw, x: int, y0: int, y1: int, color=INK) -> None:
    draw.line((x, y0, x, y1 + 9), fill=color, width=3)
    draw.polygon([(x, y1), (x - 7, y1 + 12), (x + 7, y1 + 12)], fill=color)


def box(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    subtitle: str | None,
    kind: str,
) -> tuple[int, int, int, int]:
    fill, stroke = KIND[kind]
    stroke_w = 3 if kind in {"gate", "agent", "det"} else 2
    rounded(draw, (x, y, x + w, y + h), fill, stroke, width=stroke_w, radius=11)
    if kind in {"agent", "det", "gate"}:
        draw.rectangle((x + 3, y + 10, x + 9, y + h - 10), fill=stroke)
    title_f = font(16, bold=True)
    sub_f = font(12)
    cx = x + w / 2
    if subtitle:
        center_text(draw, (cx, y + h / 2 - 11), title, title_f, INK)
        wrap_center(draw, cx, y + h / 2 + 10, subtitle, sub_f, w - 18, MUTED)
    else:
        center_text(draw, (cx, y + h / 2), title, title_f, INK)
    return (x, y, x + w, y + h)


def layer_band(draw: ImageDraw.ImageDraw, y: int, h: int, label: str, x1: int | None = None) -> None:
    right = x1 if x1 is not None else W - 48
    rounded(draw, (48, y, right, y + h), LAYER, LINE, width=1, radius=14)
    draw.text((68, y + 10), label, font=font(13, bold=True), fill=MUTED)


def legend_swatch(draw: ImageDraw.ImageDraw, x: int, y: int, kind: str, label: str) -> None:
    fill, stroke = KIND[kind]
    rounded(draw, (x, y, x + 34, y + 20), fill, stroke, 2, 5)
    draw.text((x + 44, y + 1), label, font=font(14), fill=INK)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.text((64, 28), "ForecastWize — Agentic AI Forecasting Architecture", font=font(34, bold=True), fill=INK)
    draw.text(
        (64, 76),
        "Business and operations forecasting: agents interpret evidence; Python owns every number.",
        font=font(17),
        fill=MUTED,
    )

    legend_swatch(draw, 64, 118, "agent", "Agent = decision / interpretation")
    legend_swatch(draw, 430, 118, "det", "Deterministic engine = numerical computation")
    legend_swatch(draw, 900, 118, "gate", "Validation gate")
    draw.line((1180, 128, 1244, 128), fill=CHALLENGE, width=3)
    draw.text((1254, 119), "Challenge / re-evaluation (bounded)", font=font(14), fill=CHALLENGE)

    # --- 1 Presentation ---
    layer_band(draw, 156, 88, "1  Presentation layer")
    box(draw, 72, 186, 1360, 46, "Next.js  ·  TypeScript dashboard", None, "plain")
    box(draw, 1460, 186, 1348, 46, "Analyst workspace: upload, run, review, evaluation", None, "plain")
    arrow_down(draw, 1440, 244, 268)

    # --- 2 API ---
    layer_band(draw, 268, 86, "2  API layer")
    box(draw, 72, 298, 860, 44, "FastAPI  ·  typed request / response", None, "plain")
    box(draw, 960, 298, 860, 44, "Human checkpoint  ·  explicit accept / reject", None, "gate")
    box(draw, 1850, 298, 958, 44, "Runs, evidence IDs, trajectory", None, "plain")
    arrow_down(draw, 1440, 342, 374)

    # --- 3 Orchestration ---
    layer_band(draw, 374, 452, "3  Agent orchestration  ·  LangGraph / typed state machine")
    draw.text(
        (72, 402),
        "Orchestrator keeps typed state, passes evidence, and bounds retries. Agents never invent yhat, WIS, or intervals.",
        font=font(13),
        fill=MUTED,
    )

    flow_y, flow_h = 436, 68
    steps: list[tuple[str, str, str]] = [
        ("User / data upload", "CSV / Excel", "plain"),
        ("Ingestion & validation", "schema · size · parse", "det"),
        ("Data Detective", "quality · outliers · gaps", "agent"),
        ("Forecast Strategist", "candidates · strategy", "agent"),
        ("Context Analyst", "facts vs hypotheses", "agent"),
    ]
    inner = 2752
    gap_x = 16
    bw = (inner - 4 * gap_x) // 5
    x = 64
    flow_boxes: list[tuple[int, int, int, int]] = []
    for title, sub, kind in steps:
        b = box(draw, x, flow_y, bw, flow_h, title, sub, kind)
        flow_boxes.append(b)
        x += bw + gap_x
    for i in range(len(flow_boxes) - 1):
        arrow_right(draw, flow_boxes[i][2], flow_y + flow_h // 2, flow_boxes[i + 1][0], ACCENT)

    engine_y = 528
    engine = box(
        draw,
        64,
        engine_y,
        2752,
        62,
        "Deterministic Forecasting Engine  (tools only)",
        "Profiling  ·  cleaning  ·  statistical / ML fit  ·  backtest  ·  metrics  ·  intervals  ·  reproducibility",
        "det",
    )
    ctx = flow_boxes[4]
    ctx_cx = (ctx[0] + ctx[2]) // 2
    arrow_down(draw, ctx_cx, flow_y + flow_h, engine_y, DET_STROKE)
    arrow_down(draw, 1440, engine[3], 614, ACCENT)

    v_y, v_h = 614, 68
    verifier = box(draw, 160, v_y, 500, v_h, "Forecast Verifier", "challenge quality  ·  PASS / WARN / FAIL", "agent")
    arrow_right(draw, verifier[2], v_y + v_h // 2, 720, GATE_STROKE)
    gate = box(draw, 730, v_y, 500, v_h, "Validation gate", "weak result  →  retry or human review", "gate")
    arrow_right(draw, gate[2], v_y + v_h // 2, 1290, ACCENT)
    analyst = box(draw, 1300, v_y, 500, v_h, "Forecast Analyst", "explain drivers  ·  cite evidence", "agent")
    arrow_right(draw, analyst[2], v_y + v_h // 2, 1860, ACCENT)
    box(draw, 1870, v_y, 946, v_h, "Final forecast + explanation + insights", "numbers from engine  ·  narrative from evidence", "output")

    loop_top = 702
    box(
        draw,
        160,
        loop_top,
        1070,
        52,
        "Challenge / re-evaluation",
        "FAIL  →  Strategist + engine re-run  →  verify again  ·  bounded; else human review",
        "gate",
    )
    down_x = verifier[0] + 90
    draw.line((down_x, verifier[3], down_x, loop_top), fill=CHALLENGE, width=3)
    retry_x = 695
    draw.line((retry_x, loop_top, retry_x, engine[3] + 10), fill=CHALLENGE, width=3)
    arrow_up(draw, retry_x, engine[3] + 10, engine[3], CHALLENGE)
    draw.text(
        (1260, loop_top + 16),
        "Does not auto-approve. Exhausted retries escalate.",
        font=font(13),
        fill=CHALLENGE,
    )

    # --- 4 Deterministic tools ---
    layer_band(draw, 844, 228, "4  Deterministic forecasting & analytics  ·  Pandas  ·  NumPy  ·  scikit-learn  ·  statsmodels  ·  Pydantic")
    tools: list[tuple[str, str]] = [
        ("Data profiling", "det"),
        ("Cleaning / validation", "det"),
        ("Feature engineering", "det"),
        ("Statistical forecasting", "det"),
        ("ML forecasting", "det"),
        ("Model comparison", "det"),
        ("Backtesting", "det"),
        ("Forecast metrics", "det"),
        ("Prediction intervals", "det"),
        ("Anomaly detection", "det"),
        ("Consistency checks", "det"),
        ("Optional LightGBM / XGB", "plain"),
    ]
    tw, th, tgap = 440, 54, 16
    start_x, start_y = 72, 880
    for i, (name, kind) in enumerate(tools):
        col, row = i % 6, i // 6
        xx = start_x + col * (tw + tgap)
        yy = start_y + row * (th + tgap)
        box(draw, xx, yy, tw, th, name, None, kind)

    # --- 5 Data / 6 Observability ---
    mid = 1428
    layer_band(draw, 1092, 196, "5  Data layer", x1=mid - 12)
    rounded(draw, (mid, 1092, W - 48, 1288), LAYER, LINE, 1, 14)
    draw.text((mid + 20, 1102), "6  Observability / audit layer", font=font(13, bold=True), fill=MUTED)

    data_items = [
        ("Uploaded CSV / Excel / business datasets", "det"),
        ("Normalized time-series", "det"),
        ("Forecast results (yhat, intervals)", "det"),
        ("Evidence and execution state", "agent"),
    ]
    for i, (name, kind) in enumerate(data_items):
        box(draw, 72 + (i % 2) * 668, 1132 + (i // 2) * 70, 648, 58, name, None, kind)

    obs = [
        "Agent decisions",
        "Evidence used",
        "Model selected",
        "Metrics",
        "Validation results",
        "Forecast version",
        "Trajectory log",
        "Reproducibility",
    ]
    for i, name in enumerate(obs):
        col, row = i % 4, i // 4
        box(draw, mid + 20 + col * 348, 1132 + row * 70, 332, 58, name, None, "agent" if i in {0, 1, 6} else "plain")

    # --- Outputs ---
    layer_band(draw, 1308, 116, "Outputs")
    outputs = [
        ("Forecast values", "det"),
        ("Prediction intervals", "det"),
        ("Accuracy metrics", "det"),
        ("Backtest results", "det"),
        ("Trend / seasonality", "det"),
        ("Anomalies", "det"),
        ("Reliability", "det"),
        ("Change explanation", "agent"),
        ("Actionable insights", "agent"),
    ]
    ow = 292
    for i, (name, kind) in enumerate(outputs):
        box(draw, 64 + i * (ow + 10), 1344, ow, 60, name, None, kind)

    rounded(draw, (64, 1452, W - 64, 1640), SURFACE, AGENT_STROKE, 2, 14)
    center_text(
        draw,
        (W / 2, 1492),
        "Core principle:  AI agents do not invent numerical forecasts",
        font(22, bold=True),
        AGENT_STROKE,
    )
    wrap_center(
        draw,
        W / 2,
        1534,
        "Deterministic Python trains models, generates yhat, calculates metrics, runs backtests, and builds prediction intervals. Agents profile evidence, select strategy, challenge weak results, and explain outcomes.",
        font(16),
        2520,
        MUTED,
    )
    wrap_center(
        draw,
        W / 2,
        1588,
        "Strategy selection is valid only with deterministic backtest evidence. Human checkpoints remain explicit. Retries are bounded; exhausted paths escalate rather than looping forever.",
        font(15),
        2520,
        MUTED,
    )

    draw.text(
        (64, H - 40),
        "ForecastWize  ·  layered architecture for hackathon submission  ·  agents reason  ·  Python computes",
        font=font(13),
        fill=MUTED,
    )

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PNG, "PNG", dpi=(192, 192))
    print(f"wrote {OUT_PNG} {img.size}")


if __name__ == "__main__":
    main()
