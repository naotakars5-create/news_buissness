"""ちば営業朝刊 管理画面（Streamlit）。

起動: streamlit run app.py

タブ:
  1. 原稿作成        … AI自動生成 / 選択ネタから生成 / 手動入力 / 心理テーマ・文字量指定 / 保存・承認
  2. ネタ一覧        … 巡回取得 / スコア表示 / 除外ネタ表示 / 使う選択 / 出典リンク
  3. 原稿確認・承認  … 承認切替 / LINEプレビュー / テスト配信 / 本配信
  4. 配信ログ        … 成功・失敗者の確認
  5. 読者管理        … 購読者と支払い判定
  6. 設定            … 接続状況・ソース・除外語・しきい値の確認

完全自動ではなく、ここで原稿を確認・承認してから配信する設計。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from chiba_asakan.config import load_config
from chiba_asakan.delivery import (
    TEST_MESSAGE,
    deliver,
    mark_manuscript_sent,
    send_line_test,
    send_manuscript_test,
    should_deliver,
)
from chiba_asakan.line_flex import (
    DEFAULT_BODY_MAX,
    DEFAULT_COLORS,
    DEFAULT_TITLES,
)
from chiba_asakan.logging_config import setup_logging
from chiba_asakan.models import (
    LENGTH_PRESETS,
    PSYCHOLOGY_THEMES,
    SECTIONS,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_SENT,
    Manuscript,
    format_date_ja,
    quote_talk,
)
from chiba_asakan.pipeline import collect_and_store
from chiba_asakan.source_store import SourceItemStore
from chiba_asakan.storage import ManuscriptStore
from chiba_asakan.stripe_filter import resolve_paid_subscribers
from chiba_asakan.subscribers import load_subscribers

st.set_page_config(page_title="ちば営業朝刊 管理画面", page_icon="☀️", layout="wide")

STATUS_LABEL = {
    STATUS_DRAFT: "📝 下書き",
    STATUS_APPROVED: "✅ 承認済み",
    STATUS_SENT: "📤 配信済み",
}

# AI生成結果を受け渡すためのセッションキー（新9項目構成）
AI_FIELDS = ["theme", "chiba_topic", "why_sales", "target_audience", "deal_usage",
             "sales_talk", "rebuttal", "psychology_theme", "psychology", "action"]


def _flex_style_from_state(date_str: str) -> dict:
    """セッションに保存されたカード設定（色・本文量）を style dict にする。"""
    return {
        "colors": {
            "chiba": st.session_state.get(f"col_chiba_{date_str}", DEFAULT_COLORS["chiba"]),
            "talk": st.session_state.get(f"col_talk_{date_str}", DEFAULT_COLORS["talk"]),
            "psych": st.session_state.get(f"col_psych_{date_str}", DEFAULT_COLORS["psych"]),
        },
        "body_max": st.session_state.get(f"bodymax_{date_str}", DEFAULT_BODY_MAX),
    }


def _render_card_preview(manuscript: Manuscript, style: dict) -> None:
    """3枚カードを Streamlit 上で視覚的にプレビュー（LINE Flexの近似表示）。"""
    colors = {**DEFAULT_COLORS, **(style.get("colors") or {})}
    bmax = style.get("body_max", DEFAULT_BODY_MAX)
    m = manuscript

    def clip(t: str) -> str:
        t = (t or "").strip()
        return (t[:bmax].rstrip() + "…") if bmax and len(t) > bmax else (t or "（未入力）")

    url = m.first_source_url()
    btn = (
        f'<div style="margin-top:10px"><span style="border:1px solid {{c}};color:{{c}};'
        f'border-radius:8px;padding:5px 10px;font-size:11px">📎 出典を見る</span></div>'
        if url else ""
    )

    def card(color, icon, title, subtitle, blocks, tag):
        inner = "".join(
            (f'<div style="font-size:11px;font-weight:bold;color:{color};margin-top:8px">{lbl}</div>'
             if lbl else "")
            + f'<div style="font-size:12.5px;color:#333;line-height:1.5">{body}</div>'
            for lbl, body in blocks
        )
        tag_html = (
            f'<div style="margin-top:8px"><span style="background:{color}1A;color:{color};'
            f'border-radius:8px;padding:3px 8px;font-size:11px;font-weight:bold">{tag}</span></div>'
            if tag else ""
        )
        return (
            f'<div style="border:1px solid #eee;border-radius:14px;overflow:hidden;'
            f'box-shadow:0 1px 4px rgba(0,0,0,.08)">'
            f'<div style="background:{color};color:#fff;padding:12px 14px">'
            f'<div style="font-weight:bold;font-size:15px">{icon} {title}</div>'
            f'<div style="font-size:12px;opacity:.9">{subtitle}</div></div>'
            f'<div style="padding:12px 14px">{inner}{tag_html}{btn.format(c=color)}</div></div>'
        )

    cols = st.columns(3)
    with cols[0]:
        st.markdown(card(
            colors["chiba"], "📍", DEFAULT_TITLES["chiba"], clip(m.theme) if m.theme else " ",
            [("", clip(m.chiba_topic)), ("💡 営業マンが見るべき理由", clip(m.why_sales))],
            "🎯 刺さる: " + (clip(m.target_audience) if m.target_audience else "営業全般"),
        ), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(card(
            colors["talk"], "🗣", DEFAULT_TITLES["talk"],
            "刺さる: " + (m.target_audience[:30] if m.target_audience else "営業全般"),
            [("", clip(quote_talk(m.sales_talk))), ("↩️ 切り返し例", clip(m.rebuttal)),
             ("🤝 商談での使い方", clip(m.deal_usage))],
            None,
        ), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(card(
            colors["psych"], "🧠", DEFAULT_TITLES["psych"], "テーマ：" + (m.psychology_theme or "—"),
            [("", clip(m.psychology)), ("✅ 今日のアクション", clip(m.action))],
            None,
        ), unsafe_allow_html=True)


@st.cache_resource
def _bootstrap():
    cfg = load_config()
    setup_logging(cfg.log_dir)
    return cfg, ManuscriptStore(cfg.manuscript_dir), SourceItemStore(cfg.source_item_dir)


cfg, store, source_store = _bootstrap()


def _today() -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(cfg.timezone)).date()
    except Exception:  # noqa: BLE001
        return date.today()


# ---------------------------------------------------------------------------
# サイドバー
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    st.sidebar.title("☀️ ちば営業朝刊")
    st.sidebar.caption("管理画面")
    st.sidebar.divider()
    st.sidebar.subheader("接続状態")
    st.sidebar.write(("🟢" if cfg.has_line() else "🔴") + " LINE トークン")
    st.sidebar.write(("🟢" if cfg.has_ai() else "🔴") + " Anthropic (AI生成)")
    if cfg.require_stripe_paid:
        st.sidebar.write(("🟢" if cfg.has_stripe() else "🔴") + " Stripe (ライブ照会)")
    else:
        st.sidebar.write("⚪ Stripe 照会オフ（CSVのpaid列で判定）")
    st.sidebar.write(f"📇 購読者: `{cfg.subscriber_source}`")
    st.sidebar.write(f"🤖 モデル: `{cfg.ai_model}`")
    st.sidebar.write(f"🎯 候補しきい値: `{cfg.score_threshold}点`")
    missing = cfg.missing_for_delivery()
    if missing:
        st.sidebar.warning("配信に不足:\n\n- " + "\n- ".join(missing))


# ---------------------------------------------------------------------------
# 共通: 原稿の編集フォーム
# ---------------------------------------------------------------------------
def _render_manuscript_form(date_str: str, manuscript: Manuscript) -> None:
    with st.form(key=f"edit_form_{date_str}"):
        theme_default = st.session_state.get(f"ms_{date_str}_theme", manuscript.theme)
        theme = st.text_input("今日のテーマ", value=theme_default, key=f"ms_{date_str}_theme")

        values: dict[str, str] = {}
        # 心理テーマはセレクトで
        psy_default = st.session_state.get(
            f"ms_{date_str}_psychology_theme", manuscript.psychology_theme
        )
        psy_options = PSYCHOLOGY_THEMES.copy()
        psy_index = psy_options.index(psy_default) if psy_default in psy_options else 0

        for key, heading in SECTIONS:
            if key == "psychology":
                values["psychology_theme"] = st.selectbox(
                    "営業心理テーマ", psy_options, index=psy_index,
                    key=f"ms_{date_str}_psychology_theme",
                )
                values[key] = st.text_area(
                    f"■ {heading}",
                    value=st.session_state.get(f"ms_{date_str}_{key}", getattr(manuscript, key)),
                    height=130, key=f"ms_{date_str}_{key}",
                )
            else:
                values[key] = st.text_area(
                    f"■ {heading}",
                    value=st.session_state.get(f"ms_{date_str}_{key}", getattr(manuscript, key)),
                    height=130, key=f"ms_{date_str}_{key}",
                )

        # 出典（読み取り表示。生成時に自動付与される）
        if manuscript.sources:
            st.caption("出典: " + " / ".join(f"{s.get('name')}（{s.get('url')}）" for s in manuscript.sources))

        c1, c2, c3 = st.columns(3)
        save_btn = c1.form_submit_button("💾 保存（下書き）", use_container_width=True)
        approve_btn = c2.form_submit_button("✅ 保存して承認", type="primary", use_container_width=True)
        unapprove_btn = c3.form_submit_button("↩️ 承認を取り消す", use_container_width=True)

    if save_btn or approve_btn or unapprove_btn:
        manuscript.theme = theme
        manuscript.psychology_theme = values.get("psychology_theme", manuscript.psychology_theme)
        for key, _ in SECTIONS:
            setattr(manuscript, key, values[key])
        if approve_btn:
            if manuscript.is_complete():
                manuscript.status = STATUS_APPROVED
            else:
                st.error("未入力のため承認できません: " + " / ".join(manuscript.missing_sections()))
                manuscript.status = STATUS_DRAFT
        elif unapprove_btn:
            manuscript.status = STATUS_DRAFT
        elif save_btn and manuscript.status == STATUS_APPROVED:
            manuscript.status = STATUS_DRAFT
        store.save(manuscript)
        st.success(f"保存しました（{STATUS_LABEL.get(manuscript.status)} / 本文 約{manuscript.char_count()}字）")
        st.rerun()

    st.divider()
    st.subheader("LINE プレビュー")
    st.text(manuscript.to_line_text())


def _candidate_records(date_str: str):
    return source_store.candidates(date_str, cfg.score_threshold)


# ---------------------------------------------------------------------------
# タブ: LINEテスト配信（AI APIキー不要）
# ---------------------------------------------------------------------------
def tab_line_test() -> None:
    st.header("🧪 LINEテスト配信")
    st.caption(
        "AI APIキーがなくても、LINEへの配信設定だけを確認できます。"
        "必要なのは LINE_CHANNEL_ACCESS_TOKEN と LINE_TEST_USER_ID の2つだけ"
        "（LINE_CHANNEL_SECRET は不要）。"
    )

    # 設定状況（値そのものは表示しない＝設定済み/未設定のみ）
    c1, c2 = st.columns(2)
    c1.write(("🟢 設定済み" if cfg.has_line() else "🔴 未設定") + "  LINE_CHANNEL_ACCESS_TOKEN")
    c2.write(("🟢 設定済み" if cfg.line_test_user_id else "🔴 未設定") + "  LINE_TEST_USER_ID")

    ready = cfg.has_line() and bool(cfg.line_test_user_id)
    if not ready:
        st.warning(
            "`.env` に **LINE_CHANNEL_ACCESS_TOKEN** と **LINE_TEST_USER_ID** を設定して、"
            "アプリを再起動してください。この2つだけでテスト配信できます。"
        )

    st.divider()
    st.subheader("① 固定メッセージを送信")
    st.code(TEST_MESSAGE, language=None)
    if st.button("📤 テストメッセージを送信", type="primary", disabled=not ready,
                 use_container_width=True):
        ok, err = send_line_test(cfg)  # 固定メッセージ
        if ok:
            st.success("✅ 送信成功！自分のLINEを確認してください。")
        else:
            st.error(f"❌ 送信失敗: {err}")
            st.caption("失敗の詳細は `logs/line_test.log` に記録しました。")

    st.divider()
    st.subheader("② 手動入力したテキストを送信")
    manual = st.text_area("送信する本文（自由入力）", value="", height=160,
                          placeholder="ここに送りたい内容を入力…", key="line_test_manual")
    if st.button("📤 この内容を送信", disabled=not ready, use_container_width=True):
        if not manual.strip():
            st.error("本文が空です。")
        else:
            ok, err = send_line_test(cfg, text=manual)
            if ok:
                st.success("✅ 送信成功！自分のLINEを確認してください。")
            else:
                st.error(f"❌ 送信失敗: {err}")
                st.caption("失敗の詳細は `logs/line_test.log` に記録しました。")


# ---------------------------------------------------------------------------
# タブ1: 原稿作成
# ---------------------------------------------------------------------------
def tab_create() -> None:
    st.header("① 原稿作成")
    target_date: date = st.date_input("配信日", value=_today(), key="create_date")
    date_str = target_date.isoformat()
    manuscript = store.get_or_create(date_str)

    st.caption(f"状態: {STATUS_LABEL.get(manuscript.status, manuscript.status)}")

    # --- 生成オプション ---
    with st.container(border=True):
        st.markdown("**🤖 AIで生成**")
        col1, col2 = st.columns(2)
        with col1:
            psy_choice = st.selectbox(
                "営業心理テーマ", ["（AIにおまかせ）"] + PSYCHOLOGY_THEMES, key="gen_psy"
            )
        with col2:
            length = st.radio(
                "文字量", LENGTH_PRESETS, horizontal=True,
                index=LENGTH_PRESETS.index(cfg.draft_length_default)
                if cfg.draft_length_default in LENGTH_PRESETS else 1,
                key="gen_len",
            )

        cands = _candidate_records(date_str)
        st.caption(f"この日の原稿候補ネタ: {len(cands)} 件（しきい値 {cfg.score_threshold}点以上）")
        label_map = {f"{r.score}点 | {r.title}（{r.source_name}）": r for r in cands}
        preselected = [lbl for lbl, r in label_map.items() if r.used_in_draft]
        chosen = st.multiselect(
            "原稿に使うネタを選択（未選択なら高得点の上位を自動使用）",
            list(label_map.keys()), default=preselected, key="gen_items",
        )

        disabled = not cfg.has_ai()
        if disabled:
            st.warning("ANTHROPIC_API_KEY が未設定のため AI 生成は使えません（手動入力は可能）。")

        bcol1, bcol2 = st.columns(2)
        gen_selected = bcol1.button("🤖 選択ネタから生成", disabled=disabled, use_container_width=True)
        gen_auto = bcol2.button("🤖 高得点ネタから自動生成", disabled=disabled, use_container_width=True)

        if gen_selected or gen_auto:
            if gen_selected:
                items = [label_map[lbl] for lbl in chosen]
                if not items:
                    st.error("ネタが選択されていません。")
                    items = None
            else:
                items = cands[:4]  # 上位4件
            if items is not None:
                with st.spinner("生成中…（数十秒かかることがあります）"):
                    try:
                        from chiba_asakan.ai_writer import generate_manuscript_dict

                        theme = None if psy_choice.startswith("（") else psy_choice
                        data = generate_manuscript_dict(cfg, target_date, items, theme, length)
                        for k in AI_FIELDS:
                            st.session_state[f"ms_{date_str}_{k}"] = data.get(k, "")
                        # 出典は原稿に保存し、使用フラグも更新
                        manuscript.sources = data.get("sources", [])
                        store.save(manuscript)
                        used_ids = {r.id for r in items}
                        if used_ids:
                            source_store.set_used(date_str, used_ids, used=True)
                        st.success("たたき台を生成しました。下のフォームで確認・編集してください。")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"生成に失敗: {exc}")

    # --- 編集フォーム ---
    _render_manuscript_form(date_str, manuscript)


# ---------------------------------------------------------------------------
# タブ2: ネタ一覧
# ---------------------------------------------------------------------------
def tab_sources() -> None:
    st.header("② ネタ一覧")

    col1, col2 = st.columns([1, 2])
    with col1:
        target_date: date = st.date_input("対象日", value=_today(), key="src_date")
    date_str = target_date.isoformat()

    with col2:
        st.write("")
        st.write("")
        if st.button("🔄 情報ソースを巡回して取得（除外判定・採点まで実行）", type="primary"):
            with st.spinner("巡回中…（ソース数により時間がかかります）"):
                try:
                    records = collect_and_store(cfg, date_str)
                    st.success(f"取得 {len(records)} 件を保存しました。")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"巡回に失敗: {exc}")

    records = source_store.load_records(date_str)
    if not records:
        st.info(
            "この日のネタはまだありません。「🔄 巡回」を押すか、`.env` の "
            "`SOURCE_FEED_OVERRIDES` でフィードURLを設定してください。"
        )
        return

    kept = [r for r in records if not r.excluded]
    excluded = [r for r in records if r.excluded]
    cands = [r for r in kept if r.score >= cfg.score_threshold]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("取得", len(records))
    c2.metric(f"候補(≥{cfg.score_threshold})", len(cands))
    c3.metric("採用外(低得点)", len(kept) - len(cands))
    c4.metric("除外", len(excluded))

    # --- 残ったネタ ---
    st.subheader("📰 ネタ（除外されていないもの・高得点順）")
    rows = [
        {
            "使う": r.used_in_draft,
            "score": r.score,
            "title": r.title,
            "source": r.source_name,
            "area": r.area,
            "category": r.category,
            "published": r.published_at,
            "url": r.url,
            "理由": r.score_reason,
        }
        for r in sorted(kept, key=lambda x: x.score, reverse=True)
    ]
    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "url": st.column_config.LinkColumn("出典", display_text="開く"),
            "使う": st.column_config.CheckboxColumn("使う"),
            "score": st.column_config.NumberColumn("点", width="small"),
        },
    )

    # 「使う」選択の保存（multiselectで確実に）
    label_map = {f"{r.score}点 | {r.title}": r for r in sorted(kept, key=lambda x: x.score, reverse=True)}
    used_default = [lbl for lbl, r in label_map.items() if r.used_in_draft]
    selected = st.multiselect(
        "原稿に使うネタを選択", list(label_map.keys()), default=used_default, key="src_used"
    )
    cbtn1, cbtn2 = st.columns(2)
    if cbtn1.button("💾 使うネタを保存", use_container_width=True):
        all_ids = {r.id for r in kept}
        chosen_ids = {label_map[lbl].id for lbl in selected}
        source_store.set_used(date_str, all_ids, used=False)
        source_store.set_used(date_str, chosen_ids, used=True)
        st.success(f"{len(chosen_ids)} 件を「使う」に設定しました。")
        st.rerun()
    if cbtn2.button("✍️ 選択ネタから原稿を生成（下書き保存）", type="primary",
                    disabled=not cfg.has_ai(), use_container_width=True):
        items = [label_map[lbl] for lbl in selected]
        if not items:
            st.error("ネタが選択されていません。")
        elif not cfg.has_ai():
            st.error("ANTHROPIC_API_KEY が未設定です。")
        else:
            with st.spinner("生成中…"):
                try:
                    from chiba_asakan.ai_writer import generate_manuscript

                    m = generate_manuscript(cfg, target_date, items, target_length=cfg.draft_length_default)
                    store.save(m)
                    source_store.set_used(date_str, {r.id for r in items}, used=True)
                    st.success("下書きを生成・保存しました。「① 原稿作成」または「③ 原稿確認・承認」で確認してください。")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"生成に失敗: {exc}")

    # --- 除外ネタ ---
    if excluded:
        with st.expander(f"🚫 除外されたネタ {len(excluded)} 件（理由つき）", expanded=False):
            ex_rows = [
                {
                    "title": r.title,
                    "source": r.source_name,
                    "exclude_reason": r.exclude_reason,
                    "matched": ", ".join(r.exclude_matched),
                    "url": r.url,
                }
                for r in excluded
            ]
            st.dataframe(
                ex_rows, use_container_width=True, hide_index=True,
                column_config={"url": st.column_config.LinkColumn("出典", display_text="開く")},
            )


# ---------------------------------------------------------------------------
# タブ3: 原稿確認・承認
# ---------------------------------------------------------------------------
def tab_review() -> None:
    st.header("③ 原稿確認・承認")
    manuscripts = store.list_manuscripts()
    if not manuscripts:
        st.info("まだ原稿がありません。「① 原稿作成」から作成してください。")
        return

    options = {f"{m.date}  {STATUS_LABEL.get(m.status, m.status)}": m.date for m in manuscripts}
    label = st.selectbox("原稿を選択", list(options.keys()))
    date_str = options[label]
    manuscript = store.load(date_str)
    if manuscript is None:
        st.error("原稿の読み込みに失敗しました。")
        return

    st.caption(
        f"配信日: {format_date_ja(manuscript.date_obj)} ／ "
        f"状態: {STATUS_LABEL.get(manuscript.status, manuscript.status)} ／ "
        f"本文 約 {manuscript.char_count()} 字"
    )
    if not manuscript.is_complete():
        st.warning("未入力: " + " / ".join(manuscript.missing_sections()))

    # --- カードのデザイン調整（色・本文量） ---
    with st.expander("🎨 カードのデザイン調整（色・本文量）", expanded=False):
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.color_picker("千葉ネタ（青）", DEFAULT_COLORS["chiba"], key=f"col_chiba_{date_str}")
        cc2.color_picker("営業トーク（緑）", DEFAULT_COLORS["talk"], key=f"col_talk_{date_str}")
        cc3.color_picker("心理（オレンジ）", DEFAULT_COLORS["psych"], key=f"col_psych_{date_str}")
        cc4.slider("1カード本文の最大文字数", 60, 400, DEFAULT_BODY_MAX, key=f"bodymax_{date_str}")
    style = _flex_style_from_state(date_str)

    # --- プレビュー（カード / テキスト） ---
    pv1, pv2 = st.tabs(["🪪 カードプレビュー（3枚）", "📄 テキスト表示"])
    with pv1:
        _render_card_preview(manuscript, style)
        st.caption("※ LINE Flexの近似表示です。実機の見え方はテスト配信で確認してください。")
    with pv2:
        st.text(manuscript.to_line_text())

    st.divider()
    op1, op2 = st.columns(2)

    # --- 承認 + テスト配信 ---
    with op1:
        st.subheader("承認 / テスト配信")
        if manuscript.status != STATUS_APPROVED:
            if st.button("✅ この原稿を承認する", type="primary", use_container_width=True,
                         disabled=not manuscript.is_complete()):
                manuscript.status = STATUS_APPROVED
                store.save(manuscript)
                st.success("承認しました。")
                st.rerun()
        else:
            if st.button("↩️ 承認を取り消す", use_container_width=True):
                manuscript.status = STATUS_DRAFT
                store.save(manuscript)
                st.rerun()

        st.markdown("**🧪 テスト配信（自分のLINEへ）**")
        if not cfg.line_test_user_id:
            st.caption("`.env` の `LINE_TEST_USER_ID` を設定すると使えます。")
        test_mode = st.radio("送信形式", ["カード（Flex）", "テキスト"], horizontal=True,
                             key=f"testmode_{date_str}")
        if st.button("自分に送ってみる", disabled=not cfg.line_test_user_id,
                     use_container_width=True):
            ok, err, used = send_manuscript_test(
                cfg, manuscript, use_flex=test_mode.startswith("カード"), flex_style=style
            )
            if ok:
                st.success(f"送信しました（{used}）。LINEを確認してください。")
            else:
                st.error(f"失敗: {err}")
                st.caption("詳細は logs/line_test.log に記録しました。")

    # --- 本配信（Flex標準） ---
    with op2:
        st.subheader("📤 本配信（Flex標準・失敗時テキスト）")
        ok, reason = should_deliver(manuscript)
        missing = cfg.missing_for_delivery()
        try:
            subs = load_subscribers(cfg)
            resolution = resolve_paid_subscribers(subs, cfg)
            target = resolution.target_count
        except Exception as exc:  # noqa: BLE001
            subs, resolution, target = None, None, 0
            st.error(f"購読者読み込み失敗: {exc}")

        if st.button("📊 ドライラン（対象者数を確認）", use_container_width=True):
            res = deliver(cfg, manuscript, dry_run=True)
            st.success(f"配信対象 {res.target_count} 名（実送信なし）")

        if not ok:
            st.info(f"本配信できません: {reason}")
        if missing:
            st.error("設定不足:\n\n- " + "\n- ".join(missing))
        confirm = st.checkbox(f"内容を確認しました。{target} 名に配信します", key=f"confirm_{date_str}")
        send_disabled = not (ok and not missing and target > 0 and confirm and subs is not None)
        if st.button("📤 LINEで本配信（カード）", type="primary", disabled=send_disabled,
                     use_container_width=True):
            with st.spinner("配信中…"):
                result = deliver(cfg, manuscript, dry_run=False, subscribers=subs,
                                 use_flex=True, flex_style=style)
                mark_manuscript_sent(manuscript, result)
                store.save(manuscript)
            st.success(f"配信完了：成功 {result.sent_count} ／ 失敗 {result.failed_count}")
            if result.failures:
                st.error("失敗者: " + ", ".join(r.name or r.line_user_id for r in result.failures))
            st.caption(f"ログ: {Path(result.log_path).name}")


# ---------------------------------------------------------------------------
# タブ4: 配信ログ
# ---------------------------------------------------------------------------
def tab_logs() -> None:
    st.header("④ 配信ログ")
    log_files = sorted(cfg.delivery_log_dir.glob("*.json"), reverse=True)
    if not log_files:
        st.info("まだ配信ログがありません。")
        return
    selected = st.selectbox("ログを選択", [p.name for p in log_files])
    try:
        data = json.loads((cfg.delivery_log_dir / selected).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        st.error(f"ログ読み込み失敗: {exc}")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("配信対象", data.get("target_count", 0))
    c2.metric("成功", data.get("sent_count", 0))
    c3.metric("失敗", data.get("failed_count", 0))
    c4.metric("ドライラン", "はい" if data.get("dry_run") else "いいえ")
    st.caption(
        f"開始 {data.get('started_at')} ／ 終了 {data.get('finished_at')} ／ "
        f"未払い {data.get('skipped_unpaid', 0)} ／ 配信OFF {data.get('skipped_inactive', 0)} ／ "
        f"Stripe照会エラー {data.get('stripe_errors', 0)}"
    )
    results = data.get("results", [])
    failures = [r for r in results if r.get("status") == "failed"]
    if failures:
        st.subheader(f"❌ 失敗者 {len(failures)} 名")
        st.dataframe(failures, use_container_width=True, hide_index=True)
    st.subheader("全件")
    st.dataframe(results, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# タブ5: 読者管理
# ---------------------------------------------------------------------------
def tab_subscribers() -> None:
    st.header("⑤ 読者管理")
    st.caption(f"ソース: `{cfg.subscriber_source}`")
    try:
        subs = load_subscribers(cfg)
    except Exception as exc:  # noqa: BLE001
        st.error(f"購読者の読み込みに失敗: {exc}")
        return
    if not subs:
        st.info("購読者がいません。`data/subscribers.csv` を作成してください。")
        return
    try:
        resolution = resolve_paid_subscribers(subs, cfg)
    except Exception as exc:  # noqa: BLE001
        st.error(f"支払い判定に失敗: {exc}")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("合計", len(subs))
    c2.metric("配信対象", resolution.target_count)
    c3.metric("未払い", len(resolution.unpaid))
    c4.metric("配信OFF", len(resolution.inactive))
    paid_ids = {s.line_user_id for s in resolution.paid}
    rows = [
        {
            "line_user_id": s.line_user_id, "name": s.name,
            "stripe_customer_id": s.stripe_customer_id, "active": s.active,
            "paid_flag": s.paid, "配信対象": "✅" if s.line_user_id in paid_ids else "—",
            "note": s.note,
        }
        for s in subs
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# タブ6: 設定
# ---------------------------------------------------------------------------
def tab_settings() -> None:
    st.header("⑥ 設定（確認用）")
    st.caption("値の変更は `.env` を編集してアプリを再起動してください。")

    st.subheader("接続")
    st.write({
        "LINE": cfg.has_line(),
        "Anthropic(AI)": cfg.has_ai(),
        "Stripe": cfg.has_stripe(),
        "REQUIRE_STRIPE_PAID": cfg.require_stripe_paid,
        "AI_MODEL": cfg.ai_model,
        "SCORING_MODE": cfg.scoring_mode,
        "SCORE_THRESHOLD": cfg.score_threshold,
        "DRAFT_LENGTH_DEFAULT": cfg.draft_length_default,
        "TIMEZONE": cfg.timezone,
        "LINE_TEST_USER_ID設定": bool(cfg.line_test_user_id),
    })

    st.subheader("情報ソース")
    st.write("有効ソース: " + ", ".join(cfg.enabled_sources))
    if cfg.source_feed_overrides:
        st.write("フィードURL設定済み:")
        st.json({k: v for k, v in cfg.source_feed_overrides.items()})
    else:
        st.info(
            "フィードURL未設定。`SOURCE_FEED_OVERRIDES`（JSON）で各ソースのRSS/AtomのURLを設定すると、"
            "PR TIMES 以外のソース（県・市・観光・商業）も巡回されます。"
        )

    st.subheader("除外フィルター")
    from chiba_asakan.exclusion import ALLOW_KEYWORDS, HARD_EXCLUDE, SOFT_EXCLUDE
    st.write("ハード除外: " + ", ".join(HARD_EXCLUDE + cfg.exclude_keywords_extra))
    st.write("ソフト除外（許可語があれば残す）: " + ", ".join(SOFT_EXCLUDE))
    st.write("許可語（イベント等）: " + ", ".join(ALLOW_KEYWORDS))
    st.caption("追加のハード除外語は `.env` の `EXCLUDE_KEYWORDS_EXTRA`（カンマ区切り）で足せます。")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main() -> None:
    render_sidebar()
    # AI APIキー未設定でもアプリは起動する。状態を画面上部に明示。
    if not cfg.has_ai():
        st.info(
            "AI APIキー未設定のため、自動原稿生成は使えません。"
            "手動入力とLINEテスト配信は利用できます"
        )
    tabs = st.tabs(
        ["🧪 LINEテスト配信", "① 原稿作成", "② ネタ一覧", "③ 原稿確認・承認",
         "④ 配信ログ", "⑤ 読者管理", "⑥ 設定"]
    )
    with tabs[0]:
        tab_line_test()
    with tabs[1]:
        tab_create()
    with tabs[2]:
        tab_sources()
    with tabs[3]:
        tab_review()
    with tabs[4]:
        tab_logs()
    with tabs[5]:
        tab_subscribers()
    with tabs[6]:
        tab_settings()


main()
