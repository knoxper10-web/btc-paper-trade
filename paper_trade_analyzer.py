# File: paper_trade_analyzer.py
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta


class PaperTradeAnalyzer:
    def __init__(self):
        self.history_file = 'paper_trade_history.json'
        self.performance_file = 'paper_trade_performance.csv'
        self.report_file = 'weekly_report.json'
        self.history = None
        self.performance = None

    def load_data(self):
        if not os.path.exists(self.history_file):
            print(f"⚠️ {self.history_file} が見つかりません")
            return False
        if not os.path.exists(self.performance_file):
            print(f"⚠️ {self.performance_file} が見つかりません")
            return False

        with open(self.history_file, 'r') as f:
            self.history = json.load(f)

        self.performance = pd.read_csv(self.performance_file)
        self.performance['timestamp'] = pd.to_datetime(self.performance['timestamp'])
        return True

    def analyze_trades(self):
        """取引分析"""
        result = {}
        trades = self.history.get('trades', [])
        if not trades:
            return result

        df = pd.DataFrame(trades)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # タイプ別集計
        result['trade_summary'] = df.groupby('type').size().to_dict()

        # 月次購入
        monthly = df[df['type'] == 'monthly_buy']
        if len(monthly) > 0:
            result['monthly_buy'] = {
                'count': len(monthly),
                'total_invested': float(monthly['amount_usd'].sum()),
                'total_btc': float(monthly['btc_bought'].sum()),
                'avg_price': float(monthly['price'].mean())
            }

        # 追加購入
        extra = df[df['type'] == 'extra_buy']
        if len(extra) > 0:
            total_inv = float(extra['amount_usd'].sum())
            total_btc = float(extra['btc_bought'].sum())
            result['extra_buy'] = {
                'count': len(extra),
                'total_invested': total_inv,
                'total_btc': total_btc,
                'avg_price': total_inv / total_btc if total_btc > 0 else 0
            }
            if 'multiplier' in extra.columns:
                result['extra_buy']['by_multiplier'] = (
                    extra.groupby('multiplier').size().to_dict()
                )

        # 売却
        sells = df[df['type'] == 'sell']
        if len(sells) > 0:
            total_proc = float(sells['proceeds_usd'].sum())
            total_sold = float(sells['btc_sold'].sum())
            result['sell'] = {
                'count': len(sells),
                'total_proceeds': total_proc,
                'total_btc_sold': total_sold,
                'avg_price': total_proc / total_sold if total_sold > 0 else 0
            }

        return result

    def analyze_performance(self):
        """パフォーマンス分析"""
        result = {}
        if len(self.performance) == 0:
            return result

        latest = self.performance.iloc[-1]
        first = self.performance.iloc[0]
        days = int((latest['timestamp'] - first['timestamp']).days)

        # 現在の状態
        result['current'] = {
            'days_running': days,
            'btc_holdings': float(latest['btc_holdings']),
            'cash_balance': float(latest['cash_balance']),
            'total_value': float(latest['total_value']),
            'total_invested': float(latest['total_invested']),
            'total_pnl': float(latest['total_pnl']),
            'roi_percent': float(latest['roi_percent']),
            'btc_price': float(latest['btc_price']),
            'avg_cost': float(latest['avg_cost']),
            'price_diff_percent': float((latest['btc_price']/latest['avg_cost']-1)*100)
                                  if latest['avg_cost'] > 0 else 0
        }

        # リスク指標
        max_value = float(self.performance['total_value'].max())
        min_value = float(self.performance['total_value'].min())

        # 累積最大値からのドローダウン (より正確な計算)
        equity = self.performance['total_value'].values
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak
        max_dd = float(dd.min() * 100)

        result['risk'] = {
            'max_value': max_value,
            'min_value': min_value,
            'max_drawdown_percent': max_dd
        }

        # Buy & Hold 比較
        if first['btc_price'] > 0:
            bh_return = float((latest['btc_price'] / first['btc_price'] - 1) * 100)
            result['comparison'] = {
                'strategy_roi': float(latest['roi_percent']),
                'buy_hold_roi': bh_return,
                'alpha': float(latest['roi_percent'] - bh_return)
            }

        # 直近1週間のパフォーマンス
        one_week_ago = latest['timestamp'] - timedelta(days=7)
        recent = self.performance[self.performance['timestamp'] >= one_week_ago]
        if len(recent) >= 2:
            week_start = recent.iloc[0]
            result['weekly'] = {
                'value_start': float(week_start['total_value']),
                'value_end': float(latest['total_value']),
                'change': float(latest['total_value'] - week_start['total_value']),
                'change_percent': float((latest['total_value']/week_start['total_value']-1)*100)
                                   if week_start['total_value'] > 0 else 0,
                'btc_price_start': float(week_start['btc_price']),
                'btc_price_end': float(latest['btc_price']),
                'btc_change_percent': float((latest['btc_price']/week_start['btc_price']-1)*100)
                                       if week_start['btc_price'] > 0 else 0
            }

        return result

    def evaluate(self, perf, trades):
        """評価コメントの生成"""
        comments = []
        warnings = []
        recommendations = []

        if 'comparison' in perf:
            alpha = perf['comparison']['alpha']
            if alpha > 5:
                comments.append(f"✅ Buy&Holdを{alpha:.1f}%上回る優秀な結果")
            elif alpha > 0:
                comments.append(f"🟢 Buy&Holdを{alpha:.1f}%上回り戦略が有効")
            elif alpha > -5:
                comments.append(f"🟡 Buy&Holdとほぼ同等 ({alpha:+.1f}%)")
            else:
                warnings.append(f"⚠️ Buy&Holdに{abs(alpha):.1f}%劣後。戦略の見直しを検討")

        if 'risk' in perf:
            dd = perf['risk']['max_drawdown_percent']
            if dd < -25:
                warnings.append(f"⚠️ 最大DD {dd:.1f}% は許容範囲外")
            elif dd < -15:
                comments.append(f"🟡 最大DD {dd:.1f}% は注意レベル")
            else:
                comments.append(f"✅ 最大DD {dd:.1f}% は健全")

        if 'current' in perf:
            roi = perf['current']['roi_percent']
            days = perf['current']['days_running']
            if days >= 30:
                if roi > 0:
                    comments.append(f"✅ 運用{days}日でROI {roi:+.2f}%")
                else:
                    comments.append(f"🟡 運用{days}日でROI {roi:+.2f}% (まだ短期)")

        # 取引頻度評価
        if 'extra_buy' in trades:
            count = trades['extra_buy']['count']
            days = perf.get('current', {}).get('days_running', 1)
            monthly_rate = count / max(days/30, 1)
            if monthly_rate > 3:
                recommendations.append(
                    f"💡 追加購入が月{monthly_rate:.1f}回と多い。"
                    f"buy_threshold_low を上げることを検討"
                )
            elif monthly_rate < 0.3 and days > 60:
                recommendations.append(
                    f"💡 追加購入が月{monthly_rate:.1f}回と少ない。"
                    f"buy_threshold_low を下げることを検討"
                )

        # 運用期間に応じた推奨
        if 'current' in perf:
            days = perf['current']['days_running']
            if days < 30:
                recommendations.append("💡 運用30日未満。継続して様子見を推奨")
            elif days < 90:
                recommendations.append("💡 運用90日未満。実取引判断にはまだ早い")
            else:
                if 'comparison' in perf and perf['comparison']['alpha'] > 0:
                    recommendations.append("💡 90日以上経過しBuy&Hold上回る。少額実取引を検討可")
                else:
                    recommendations.append("💡 90日以上経過したがBuy&Hold劣後。設定見直し推奨")

        return {
            'comments': comments,
            'warnings': warnings,
            'recommendations': recommendations
        }

    def generate_report(self):
        """総合レポート生成"""
        print("=" * 70)
        print("BTC Paper Trade 週次レポート生成")
        print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
        print("=" * 70)

        if not self.load_data():
            print("⚠️ データが不足しています")
            return None

        trade_analysis = self.analyze_trades()
        perf_analysis = self.analyze_performance()
        evaluation = self.evaluate(perf_analysis, trade_analysis)

        report = {
            'generated_at': datetime.now().isoformat(),
            'trades': trade_analysis,
            'performance': perf_analysis,
            'evaluation': evaluation
        }

        # JSON保存
        with open(self.report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # コンソール出力
        self.print_report(report)

        print(f"\n✅ {self.report_file} に保存しました")
        return report

    def print_report(self, report):
        """コンソールに見やすく出力"""
        perf = report['performance']
        trades = report['trades']
        ev = report['evaluation']

        if 'current' in perf:
            c = perf['current']
            print(f"\n📊 運用状況 ({c['days_running']}日経過)")
            print(f"  総資産価値  : ${c['total_value']:,.2f}")
            print(f"  総投資額    : ${c['total_invested']:,.2f}")
            print(f"  総損益      : ${c['total_pnl']:+,.2f}")
            print(f"  ROI         : {c['roi_percent']:+.2f}%")
            print(f"  BTC保有量   : {c['btc_holdings']:.6f}")
            print(f"  平均取得単価: ${c['avg_cost']:,.2f}")
            print(f"  現在価格    : ${c['btc_price']:,.2f} ({c['price_diff_percent']:+.1f}%)")

        if 'comparison' in perf:
            cmp = perf['comparison']
            print(f"\n🆚 Buy & Hold比較")
            print(f"  戦略 ROI    : {cmp['strategy_roi']:+.2f}%")
            print(f"  B&H ROI     : {cmp['buy_hold_roi']:+.2f}%")
            print(f"  アルファ    : {cmp['alpha']:+.2f}%")

        if 'risk' in perf:
            r = perf['risk']
            print(f"\n📉 リスク指標")
            print(f"  最大資産価値  : ${r['max_value']:,.2f}")
            print(f"  最小資産価値  : ${r['min_value']:,.2f}")
            print(f"  最大ドローダウン: {r['max_drawdown_percent']:.2f}%")

        if 'weekly' in perf:
            w = perf['weekly']
            print(f"\n📅 直近1週間")
            print(f"  資産変化   : ${w['change']:+,.2f} ({w['change_percent']:+.2f}%)")
            print(f"  BTC価格変化: {w['btc_change_percent']:+.2f}%")

        if 'trade_summary' in trades:
            print(f"\n📜 取引サマリー")
            for k, v in trades['trade_summary'].items():
                print(f"  {k}: {v}回")

        if ev['comments']:
            print(f"\n💬 評価")
            for c in ev['comments']:
                print(f"  {c}")
        if ev['warnings']:
            print(f"\n⚠️ 警告")
            for w in ev['warnings']:
                print(f"  {w}")
        if ev['recommendations']:
            print(f"\n💡 推奨アクション")
            for r in ev['recommendations']:
                print(f"  {r}")

        print("\n" + "=" * 70)


def main():
    analyzer = PaperTradeAnalyzer()
    analyzer.generate_report()


if __name__ == "__main__":
    main()