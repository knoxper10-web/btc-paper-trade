# File: streamlit_app.py
import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import plotly.graph_objects as go

st.set_page_config(
    page_title="BTC Paper Trade Dashboard",
    page_icon="₿",
    layout="wide"
)

st.title("₿ BTC Paper Trade Dashboard")
st.caption(f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M')} (UTC)")


@st.cache_data(ttl=300)
def load_history():
    if not os.path.exists('paper_trade_history.json'):
        return None
    with open('paper_trade_history.json', 'r') as f:
        return json.load(f)


@st.cache_data(ttl=300)
def load_performance():
    if not os.path.exists('paper_trade_performance.csv'):
        return None
    df = pd.read_csv('paper_trade_performance.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


@st.cache_data(ttl=300)
def load_weekly_report():
    if not os.path.exists('weekly_report.json'):
        return None
    with open('weekly_report.json', 'r', encoding='utf-8') as f:
        return json.load(f)


history = load_history()
performance = load_performance()
weekly_report = load_weekly_report()

if history is None or performance is None or len(performance) == 0:
    st.warning("⚠️ まだデータがありません。GitHub Actionsの初回実行をお待ちください。")
    st.stop()


# ============================================================
# タブ構成
# ============================================================
main_tab, weekly_tab = st.tabs(["📊 メインダッシュボード", "📋 週次レポート"])

# ============================================================
# メインダッシュボード
# ============================================================
with main_tab:
    latest = performance.iloc[-1]
    first = performance.iloc[0]
    days = (latest['timestamp'] - first['timestamp']).days

    st.subheader("📊 現在のステータス")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "BTC現在価格",
            f"${latest['btc_price']:,.0f}",
            f"{(latest['btc_price']/first['btc_price']-1)*100:+.1f}% (運用開始比)"
        )
    with col2:
        st.metric("総資産価値", f"${latest['total_value']:,.2f}",
                  f"${latest['total_pnl']:+,.2f}")
    with col3:
        st.metric("ROI", f"{latest['roi_percent']:+.2f}%", f"運用{days}日")
    with col4:
        st.metric("BTC保有量", f"{latest['btc_holdings']:.6f}",
                  f"平均単価 ${latest['avg_cost']:,.0f}")

    # ポートフォリオ詳細
    st.subheader("💼 ポートフォリオ詳細")
    col1, col2 = st.columns(2)

    with col1:
        btc_value = latest['btc_holdings'] * latest['btc_price']
        cash_value = latest['cash_balance']
        fig_pie = go.Figure(data=[go.Pie(
            labels=['BTC', '現金'],
            values=[btc_value, cash_value],
            hole=0.4,
            marker_colors=['#F7931A', '#2E8B57']
        )])
        fig_pie.update_layout(title="資産配分", height=350)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        st.markdown("##### 詳細データ")
        detail_data = {
            "項目": ["総投資額", "現金残高", "BTC評価額", "未実現損益", "実現損益", "総損益"],
            "金額(USD)": [
                f"${latest['total_invested']:,.2f}",
                f"${latest['cash_balance']:,.2f}",
                f"${btc_value:,.2f}",
                f"${latest['unrealized_pnl']:+,.2f}",
                f"${latest['realized_pnl']:+,.2f}",
                f"${latest['total_pnl']:+,.2f}"
            ]
        }
        st.table(pd.DataFrame(detail_data))

    # グラフ
    st.subheader("📈 パフォーマンス推移")
    g1, g2, g3, g4 = st.tabs(["資産価値", "BTC価格", "損益", "ROI"])

    with g1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=performance['timestamp'], y=performance['total_value'],
                                 name='総資産価値', line=dict(color='blue', width=2)))
        fig.add_trace(go.Scatter(x=performance['timestamp'], y=performance['total_invested'],
                                 name='総投資額', line=dict(color='gray', width=2, dash='dash')))
        fig.update_layout(height=400, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)

    with g2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=performance['timestamp'], y=performance['btc_price'],
                                 name='BTC価格', line=dict(color='orange', width=2)))
        fig.add_hline(y=latest['avg_cost'], line_dash='dash', line_color='red',
                      annotation_text=f"平均取得単価 ${latest['avg_cost']:,.0f}")
        fig.update_layout(height=400, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)

    with g3:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=performance['timestamp'], y=performance['total_pnl'],
                                 name='総損益', fill='tozeroy',
                                 line=dict(color='green', width=2)))
        fig.add_hline(y=0, line_color='black')
        fig.update_layout(height=400, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)

    with g4:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=performance['timestamp'], y=performance['roi_percent'],
                                 name='ROI(%)', fill='tozeroy',
                                 line=dict(color='purple', width=2)))
        fig.add_hline(y=0, line_color='black')
        fig.update_layout(height=400, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)

    # 取引履歴
    st.subheader("📜 取引履歴")
    trades = history.get('trades', [])
    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
        df_trades = df_trades.sort_values('timestamp', ascending=False)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("月次購入", f"{(df_trades['type']=='monthly_buy').sum()}回")
        with c2:
            st.metric("追加購入", f"{(df_trades['type']=='extra_buy').sum()}回")
        with c3:
            st.metric("売却", f"{(df_trades['type']=='sell').sum()}回")

        cols = ['timestamp', 'type', 'price', 'reason']
        if 'amount_usd' in df_trades.columns:
            cols.append('amount_usd')
        if 'btc_bought' in df_trades.columns:
            cols.append('btc_bought')
        st.dataframe(df_trades[cols].head(50), use_container_width=True, hide_index=True)


# ============================================================
# 週次レポートタブ
# ============================================================
with weekly_tab:
    if weekly_report is None:
        st.info("📅 週次レポートはまだ生成されていません。次回の日曜日に自動生成されます。")
        st.markdown("""
        週次レポートは毎週日曜日 UTC 1:00（日本時間 月曜日 10:00）に自動生成されます。
        """)
    else:
        gen_at = datetime.fromisoformat(weekly_report['generated_at'])
        st.caption(f"📅 レポート生成日時: {gen_at.strftime('%Y-%m-%d %H:%M UTC')}")

        ev = weekly_report.get('evaluation', {})

        # 評価コメント
        if ev.get('comments'):
            st.markdown("### 💬 評価")
            for c in ev['comments']:
                st.success(c)

        if ev.get('warnings'):
            st.markdown("### ⚠️ 警告")
            for w in ev['warnings']:
                st.warning(w)

        if ev.get('recommendations'):
            st.markdown("### 💡 推奨アクション")
            for r in ev['recommendations']:
                st.info(r)

        st.markdown("---")

        # パフォーマンス詳細
        perf = weekly_report.get('performance', {})

        if 'current' in perf:
            st.markdown("### 📊 運用状況")
            c = perf['current']
            cols = st.columns(3)
            with cols[0]:
                st.metric("運用日数", f"{c['days_running']}日")
                st.metric("総資産価値", f"${c['total_value']:,.2f}")
            with cols[1]:
                st.metric("ROI", f"{c['roi_percent']:+.2f}%")
                st.metric("総損益", f"${c['total_pnl']:+,.2f}")
            with cols[2]:
                st.metric("BTC保有量", f"{c['btc_holdings']:.6f}")
                st.metric("平均取得単価", f"${c['avg_cost']:,.2f}")

        if 'comparison' in perf:
            st.markdown("### 🆚 Buy & Hold 比較")
            cmp = perf['comparison']
            cols = st.columns(3)
            with cols[0]:
                st.metric("戦略ROI", f"{cmp['strategy_roi']:+.2f}%")
            with cols[1]:
                st.metric("Buy&Hold ROI", f"{cmp['buy_hold_roi']:+.2f}%")
            with cols[2]:
                delta_color = "normal" if cmp['alpha'] >= 0 else "inverse"
                st.metric("アルファ(差)", f"{cmp['alpha']:+.2f}%")

            if cmp['alpha'] > 0:
                st.success(f"✅ 戦略は Buy & Hold を {cmp['alpha']:.2f}% 上回っています")
            else:
                st.warning(f"⚠️ 戦略は Buy & Hold を {abs(cmp['alpha']):.2f}% 下回っています")

        if 'weekly' in perf:
            st.markdown("### 📅 直近1週間")
            w = perf['weekly']
            cols = st.columns(3)
            with cols[0]:
                st.metric("資産変化", f"${w['change']:+,.2f}",
                          f"{w['change_percent']:+.2f}%")
            with cols[1]:
                st.metric("BTC価格変化", f"{w['btc_change_percent']:+.2f}%")
            with cols[2]:
                st.metric("週末資産", f"${w['value_end']:,.2f}")

        if 'risk' in perf:
            st.markdown("### 📉 リスク指標")
            r = perf['risk']
            cols = st.columns(3)
            with cols[0]:
                st.metric("最大資産価値", f"${r['max_value']:,.2f}")
            with cols[1]:
                st.metric("最小資産価値", f"${r['min_value']:,.2f}")
            with cols[2]:
                dd = r['max_drawdown_percent']
                st.metric("最大ドローダウン", f"{dd:.2f}%",
                          delta_color="inverse")

        # 取引集計
        trades = weekly_report.get('trades', {})
        if trades:
            st.markdown("### 📜 取引集計")

            if 'monthly_buy' in trades:
                m = trades['monthly_buy']
                with st.expander(f"💰 月次購入 ({m['count']}回)"):
                    cols = st.columns(3)
                    with cols[0]:
                        st.metric("総投資額", f"${m['total_invested']:,.2f}")
                    with cols[1]:
                        st.metric("取得BTC", f"{m['total_btc']:.6f}")
                    with cols[2]:
                        st.metric("平均購入価格", f"${m['avg_price']:,.2f}")

            if 'extra_buy' in trades:
                e = trades['extra_buy']
                with st.expander(f"🚀 追加購入 ({e['count']}回)"):
                    cols = st.columns(3)
                    with cols[0]:
                        st.metric("総投資額", f"${e['total_invested']:,.2f}")
                    with cols[1]:
                        st.metric("取得BTC", f"{e['total_btc']:.6f}")
                    with cols[2]:
                        st.metric("平均購入価格", f"${e['avg_price']:,.2f}")
                    if 'by_multiplier' in e:
                        st.write("**倍率別内訳:**")
                        for mult, cnt in e['by_multiplier'].items():
                            st.write(f"  - {mult}x: {cnt}回")

            if 'sell' in trades:
                s = trades['sell']
                with st.expander(f"💸 売却 ({s['count']}回)"):
                    cols = st.columns(3)
                    with cols[0]:
                        st.metric("総売却額", f"${s['total_proceeds']:,.2f}")
                    with cols[1]:
                        st.metric("売却BTC", f"{s['total_btc_sold']:.6f}")
                    with cols[2]:
                        st.metric("平均売却価格", f"${s['avg_price']:,.2f}")


st.markdown("---")
st.caption("⚠️ これは仮想取引（ペーパートレード）です。実際の投資判断には使用しないでください。")