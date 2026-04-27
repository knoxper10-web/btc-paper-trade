# File: btc_paper_trade.py
import ccxt
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
import warnings
import time
import requests

warnings.filterwarnings('ignore')

class BTCPaperTrader:
    def __init__(self, config_file='paper_trade_config.json'):
        self.config_file = config_file
        self.history_file = 'paper_trade_history.json'
        self.performance_file = 'paper_trade_performance.csv'
        
        # デフォルト設定
        self.config = {
            'monthly_budget': 1000,
            'initial_btc': 0,
            'initial_cash': 10000,
            'fee': 0.001,
            'buy_threshold_low': 2.5,
            'buy_threshold_mid': 3.5,
            'buy_threshold_high': 4.5,
            'sell_threshold': 4.0,
            'sell_ratio': 0.05,
            'cooldown_days': 14,
            'start_date': datetime.now().strftime('%Y-%m-%d')
        }
        
        self.load_config()
        self.load_history()
        
    def load_config(self):
        """設定ファイルの読み込み"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                saved_config = json.load(f)
                self.config.update(saved_config)
        else:
            self.save_config()
    
    def save_config(self):
        """設定ファイルの保存"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def load_history(self):
        """取引履歴の読み込み"""
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
        else:
            self.history = {
                'trades': [],
                'portfolio': {
                    'btc': self.config['initial_btc'],
                    'cash': self.config['initial_cash'],
                    'invested': 0,
                    'realized': 0
                },
                'last_monthly_buy': None,
                'last_extra_buy': None,
                'last_sell': None
            }
    
    def save_history(self):
        """取引履歴の保存"""
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def fetch_market_data(self):
        """最新の市場データ取得"""
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 直近200日のOHLCVデータ取得
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1d', limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Fear & Greedインデックス取得
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            fg_value = int(r.json()['data'][0]['value'])
        except:
            fg_value = 50
        
        return df, fg_value
    
    def calculate_indicators(self, df, fg_value):
        """指標計算"""
        # 基本指標
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_200'] = df['close'].rolling(200).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / (loss + 1e-12)
        df['rsi'] = 100 - 100 / (1 + rs)
        
        # レンジポジション
        h30 = df['close'].rolling(30).max()
        l30 = df['close'].rolling(30).min()
        df['range_pos_30'] = (df['close'] - l30) / (h30 - l30 + 1e-12)
        
        h90 = df['close'].rolling(90).max()
        l90 = df['close'].rolling(90).min()
        df['range_pos_90'] = (df['close'] - l90) / (h90 - l90 + 1e-12)
        
        # ドローダウン
        rolling_max = df['close'].rolling(180).max()
        df['drawdown_180'] = (df['close'] - rolling_max) / rolling_max
        
        # ボラティリティ
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        df['volatility_30'] = df['log_return'].rolling(30).std()
        df['vol_zscore'] = (df['volatility_30'] - df['volatility_30'].rolling(180).mean()) \
                          / (df['volatility_30'].rolling(180).std() + 1e-12)
        
        latest = df.iloc[-1].copy()
        latest['fear_greed'] = fg_value
        
        # スコア計算
        latest['div_sma200'] = (latest['close'] - latest['sma_200']) / latest['sma_200']
        
        # 売られ過ぎスコア
        oversold = 0
        oversold += np.clip((30 - latest['rsi']) / 30, 0, 1) * 1.0
        oversold += np.clip(-latest['div_sma200'] / 0.15, 0, 1) * 1.0
        oversold += np.clip((0.2 - latest['range_pos_30']) / 0.2, 0, 1) * 0.7
        oversold += np.clip(-latest['drawdown_180'] / 0.25, 0, 1) * 1.2
        oversold += np.clip((30 - fg_value) / 30, 0, 1) * 1.0
        oversold += np.clip(latest['vol_zscore'] / 2, 0, 1) * 0.5
        latest['oversold_score'] = oversold
        
        # 買われ過ぎスコア
        overbought = 0
        overbought += np.clip((latest['rsi'] - 70) / 30, 0, 1) * 1.0
        overbought += np.clip(latest['div_sma200'] / 0.30, 0, 1) * 1.0
        overbought += np.clip((latest['range_pos_30'] - 0.8) / 0.2, 0, 1) * 0.7
        overbought += np.clip((latest['range_pos_90'] - 0.95) / 0.05, 0, 1) * 1.0
        overbought += np.clip((fg_value - 75) / 25, 0, 1) * 1.5
        latest['overbought_score'] = overbought
        
        return latest
    
    def check_signals(self, market_data):
        """取引シグナルのチェック"""
        signals = []
        today = datetime.now().date()
        current_price = market_data['close']
        
        # 月次定期購入チェック
        if self.history['last_monthly_buy'] is None or \
           datetime.strptime(self.history['last_monthly_buy'], '%Y-%m-%d').date().month != today.month:
            signals.append({
                'type': 'monthly_buy',
                'amount': self.config['monthly_budget'],
                'price': current_price,
                'reason': 'Monthly DCA purchase'
            })
        
        # 追加購入シグナル
        oversold = market_data['oversold_score']
        if self.history['last_extra_buy'] is None or \
           (datetime.now() - datetime.strptime(self.history['last_extra_buy'], '%Y-%m-%d')).days >= self.config['cooldown_days']:
            
            if oversold >= self.config['buy_threshold_high']:
                signals.append({
                    'type': 'extra_buy',
                    'amount': self.config['monthly_budget'] * 2.0,
                    'price': current_price,
                    'reason': f'Strong oversold signal (score: {oversold:.2f})',
                    'multiplier': 2.0
                })
            elif oversold >= self.config['buy_threshold_mid']:
                signals.append({
                    'type': 'extra_buy',
                    'amount': self.config['monthly_budget'] * 1.0,
                    'price': current_price,
                    'reason': f'Moderate oversold signal (score: {oversold:.2f})',
                    'multiplier': 1.0
                })
            elif oversold >= self.config['buy_threshold_low']:
                signals.append({
                    'type': 'extra_buy',
                    'amount': self.config['monthly_budget'] * 0.5,
                    'price': current_price,
                    'reason': f'Light oversold signal (score: {oversold:.2f})',
                    'multiplier': 0.5
                })
        
        # 売却シグナル
        overbought = market_data['overbought_score']
        if self.history['portfolio']['btc'] > 0 and overbought >= self.config['sell_threshold']:
            if self.history['last_sell'] is None or \
               (datetime.now() - datetime.strptime(self.history['last_sell'], '%Y-%m-%d')).days >= self.config['cooldown_days']:
                signals.append({
                    'type': 'sell',
                    'btc_amount': self.history['portfolio']['btc'] * self.config['sell_ratio'],
                    'price': current_price,
                    'reason': f'Overbought signal (score: {overbought:.2f})'
                })
        
        return signals
    
    def execute_trade(self, signal):
        """仮想取引の実行"""
        timestamp = datetime.now().isoformat()
        fee = self.config['fee']
        
        trade = {
            'timestamp': timestamp,
            'type': signal['type'],
            'price': signal['price'],
            'reason': signal['reason']
        }
        
        if signal['type'] in ['monthly_buy', 'extra_buy']:
            # 購入処理
            amount_usd = signal['amount']
            btc_bought = (amount_usd * (1 - fee)) / signal['price']
            
            self.history['portfolio']['cash'] -= amount_usd
            self.history['portfolio']['btc'] += btc_bought
            self.history['portfolio']['invested'] += amount_usd
            
            trade['amount_usd'] = amount_usd
            trade['btc_bought'] = btc_bought
            
            if signal['type'] == 'monthly_buy':
                self.history['last_monthly_buy'] = datetime.now().strftime('%Y-%m-%d')
            else:
                self.history['last_extra_buy'] = datetime.now().strftime('%Y-%m-%d')
                trade['multiplier'] = signal.get('multiplier', 1.0)
        
        elif signal['type'] == 'sell':
            # 売却処理
            btc_sold = signal['btc_amount']
            proceeds = btc_sold * signal['price'] * (1 - fee)
            
            self.history['portfolio']['btc'] -= btc_sold
            self.history['portfolio']['cash'] += proceeds
            self.history['portfolio']['realized'] += proceeds
            
            trade['btc_sold'] = btc_sold
            trade['proceeds_usd'] = proceeds
            
            self.history['last_sell'] = datetime.now().strftime('%Y-%m-%d')
        
        self.history['trades'].append(trade)
        return trade
    
    def calculate_performance(self, current_price):
        """パフォーマンス計算"""
        portfolio = self.history['portfolio']
        
        # 現在価値
        btc_value = portfolio['btc'] * current_price
        total_value = btc_value + portfolio['cash']
        
        # 損益
        total_invested = portfolio['invested']
        unrealized_pnl = btc_value - (total_invested - portfolio['realized'])
        realized_pnl = portfolio['realized'] - total_invested if portfolio['realized'] > 0 else 0
        total_pnl = total_value - self.config['initial_cash']
        
        # ROI
        roi = (total_pnl / max(total_invested, 1)) * 100 if total_invested > 0 else 0
        
        # 平均取得単価
        avg_cost = (total_invested - portfolio['realized']) / portfolio['btc'] if portfolio['btc'] > 0 else 0
        
        return {
            'timestamp': datetime.now().isoformat(),
            'btc_price': current_price,
            'btc_holdings': portfolio['btc'],
            'cash_balance': portfolio['cash'],
            'total_value': total_value,
            'total_invested': total_invested,
            'unrealized_pnl': unrealized_pnl,
            'realized_pnl': realized_pnl,
            'total_pnl': total_pnl,
            'roi_percent': roi,
            'avg_cost': avg_cost,
            'total_trades': len(self.history['trades'])
        }
    
    def save_performance(self, performance):
        """パフォーマンス記録の保存"""
        df_new = pd.DataFrame([performance])
        
        if os.path.exists(self.performance_file):
            df_existing = pd.read_csv(self.performance_file)
            df = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df = df_new
        
        df.to_csv(self.performance_file, index=False)
    
    def run_daily_check(self):
        """日次チェックの実行"""
        print("=" * 70)
        print(f"BTC Paper Trade - Daily Check ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
        print("=" * 70)
        
        # 市場データ取得
        print("\n📊 市場データ取得中...")
        df, fg_value = self.fetch_market_data()
        market_data = self.calculate_indicators(df, fg_value)
        
        current_price = market_data['close']
        print(f"✅ BTC現在価格: ${current_price:,.2f}")
        
        # シグナルチェック
        print("\n🔍 シグナル分析中...")
        signals = self.check_signals(market_data)
        
        # マーケット状況表示
        print(f"\n📈 マーケット指標:")
        print(f"  RSI(14)          : {market_data['rsi']:.1f}")
        print(f"  SMA200乖離       : {market_data['div_sma200']*100:+.1f}%")
        print(f"  180日DD          : {market_data['drawdown_180']*100:.1f}%")
        print(f"  Fear & Greed     : {fg_value}/100")
        print(f"  売られ過ぎスコア : {market_data['oversold_score']:.2f}")
        print(f"  買われ過ぎスコア : {market_data['overbought_score']:.2f}")
        
        # シグナル実行
        if signals:
            print(f"\n⚡ {len(signals)}個のシグナル検出:")
            for signal in signals:
                print(f"\n  📌 {signal['type'].upper()}")
                print(f"     理由: {signal['reason']}")
                
                if signal['type'] in ['monthly_buy', 'extra_buy']:
                    print(f"     金額: ${signal['amount']:,.0f}")
                elif signal['type'] == 'sell':
                    print(f"     BTC量: {signal['btc_amount']:.6f} BTC")
                
                # 取引実行
                trade = self.execute_trade(signal)
                print(f"     ✅ 取引完了")
        else:
            print("\n⭕ 本日のシグナルなし")
        
        # パフォーマンス計算
        performance = self.calculate_performance(current_price)
        
        print("\n💼 ポートフォリオ状況:")
        print(f"  BTC保有量        : {performance['btc_holdings']:.6f} BTC")
        print(f"  現金残高         : ${performance['cash_balance']:,.2f}")
        print(f"  総資産価値       : ${performance['total_value']:,.2f}")
        print(f"  総投資額         : ${performance['total_invested']:,.2f}")
        print(f"  未実現損益       : ${performance['unrealized_pnl']:+,.2f}")
        print(f"  実現損益         : ${performance['realized_pnl']:+,.2f}")
        print(f"  総損益           : ${performance['total_pnl']:+,.2f}")
        print(f"  ROI              : {performance['roi_percent']:+.1f}%")
        print(f"  平均取得単価     : ${performance['avg_cost']:,.2f}")
        print(f"  総取引回数       : {performance['total_trades']}")
        
        # 履歴保存
        self.save_history()
        self.save_performance(performance)
        
        print("\n✅ データ保存完了")
        print("=" * 70)
        
        return performance

def main():
    trader = BTCPaperTrader()
    trader.run_daily_check()

if __name__ == "__main__":
    main()