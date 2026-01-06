"""
Chart Generator Service
Generates candlestick charts with technical indicators using mplfinance
"""

import mplfinance as mpf
import pandas as pd
from io import BytesIO
from typing import Optional
import matplotlib.pyplot as plt
import gc


class ChartGenerator:
    """Generates trading charts for visual analysis"""

    def __init__(self):
        """Initialize chart generator with Binance-style theme"""
        self.style = mpf.make_mpf_style(
            base_mpf_style='charles',
            marketcolors=mpf.make_marketcolors(
                up='#26a69a',      # Green for bullish
                down='#ef5350',    # Red for bearish
                edge='inherit',
                wick='inherit',
                volume='inherit',
            ),
            gridcolor='#2a2e39',
            facecolor='#1e222d',
            figcolor='#1e222d',
            edgecolor='#2a2e39',
        )

    def generate_chart_image(self, df: pd.DataFrame, symbol: str, interval: str = "1H") -> BytesIO:
        """
        Generate candlestick chart with Smart Money Visual Cues (Volume Climax & Structure)
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading pair name
            interval: Timeframe label

        Returns:
            BytesIO buffer containing PNG image
        """
        try:
            # Focus on recent data (last 60 candles)
            plot_df = df.tail(60).copy() if len(df) > 60 else df.copy()

            # VALIDATION: Check required columns exist
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in plot_df.columns]
            if missing_cols:
                raise Exception(f"Missing required columns: {missing_cols}")

            # CRITICAL FIX: Drop rows with NaN in OHLCV columns BEFORE any processing
            # This prevents numpy "zero-size array" errors in mplfinance
            plot_df = plot_df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])

            # VALIDATION: Check if we have enough clean data after dropping NaN
            if len(plot_df) < 2:
                raise Exception(f"Insufficient clean data: {len(plot_df)} valid candles (need at least 2)")

            # 1. VOLUME CLIMAX DETECTION (Vectorized for efficiency)
            vol_ma = plot_df['volume'].rolling(window=20).mean()
            vol_ma = vol_ma.fillna(plot_df['volume'])  # Fill NaN with raw volume for early candles

            # Detect climax volume (>2.5x average) - vectorized operation
            is_climax = plot_df['volume'] > (vol_ma * 2.5)
            climax_signals = plot_df['low'].where(is_climax) * 0.995

            # 2. STRUCTURE - Support/Resistance levels
            recent_low = plot_df['low'].min()
            recent_high = plot_df['high'].max()

            # Build additional plot overlays
            add_plots = [
                mpf.make_addplot(climax_signals, type='scatter', markersize=40, marker='^', color='#ffd700', panel=0)
            ]

            # Bollinger Bands
            if 'bb_upper' in plot_df.columns:
                add_plots.extend([
                    mpf.make_addplot(plot_df['bb_upper'], color='#787b86', linestyle='--', width=0.8),
                    mpf.make_addplot(plot_df['bb_middle'], color='#2962ff', linestyle='-', width=1.0),
                    mpf.make_addplot(plot_df['bb_lower'], color='#787b86', linestyle='--', width=0.8),
                ])

            # EMAs
            if 'ema_50' in plot_df.columns:
                add_plots.append(mpf.make_addplot(plot_df['ema_50'], color='#ff6d00', linestyle='-', width=1.2))
            if 'ema_200' in plot_df.columns:
                add_plots.append(mpf.make_addplot(plot_df['ema_200'], color='#00bcd4', linestyle='-', width=1.5))
                
            # Horizontal Lines for S/R (Visual Guide)
            hlines = dict(hlines=[recent_low, recent_high], colors=['#4caf50', '#f44336'], linestyle=':', linewidths=0.8, alpha=0.6)

            # Create figure with HIGHER DPI
            # We override volume style slightly via make_marketcolors logic if possible, 
            # but for now, the YELLOW DOTS on price are a clearer signal for Vision AI than colored volume bars.
            fig, axes = mpf.plot(
                plot_df,
                type='candle',
                style=self.style,
                volume=True,
                addplot=add_plots,
                hlines=hlines,
                title=f'{symbol} - {interval} (Smart Money View)',
                ylabel='Price',
                ylabel_lower='Vol',
                figsize=(12, 8),
                returnfig=True,
                warn_too_much_data=200,
                tight_layout=True
            )

            # Save to buffer
            buffer = BytesIO()
            fig.savefig(buffer, format='png', dpi=120, bbox_inches='tight', facecolor='#1e222d')
            buffer.seek(0)

            plt.close(fig)
            plt.close('all')
            gc.collect()

            return buffer

        except Exception as e:
            plt.close('all')
            raise Exception(f"Failed to generate chart for {symbol}: {str(e)}")

    def generate_comparison_chart(self, df_4h: pd.DataFrame, df_1h: pd.DataFrame, symbol: str) -> BytesIO:
        """
        Generate side-by-side comparison chart (4H and 1H)

        Args:
            df_4h: 4H timeframe DataFrame
            df_1h: 1H timeframe DataFrame
            symbol: Trading pair name

        Returns:
            BytesIO buffer containing PNG image
        """
        try:
            # VALIDATION: Check if DataFrames exist
            if df_4h is None or df_1h is None:
                raise Exception(f"Missing data: 4H={df_4h is not None}, 1H={df_1h is not None}")

            # Validate required columns
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            for tf, df in [('4H', df_4h), ('1H', df_1h)]:
                missing = [c for c in required_cols if c not in df.columns]
                if missing:
                    raise Exception(f"Missing {tf} columns: {missing}")

            # CRITICAL FIX: Drop NaN rows and slice to needed data
            ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
            df_4h_clean = df_4h.dropna(subset=ohlcv_cols).tail(50)
            df_1h_clean = df_1h.dropna(subset=ohlcv_cols).tail(100)

            # VALIDATION: Check clean data length
            if len(df_4h_clean) < 2:
                raise Exception(f"Insufficient clean 4H data: {len(df_4h_clean)} candles")
            if len(df_1h_clean) < 2:
                raise Exception(f"Insufficient clean 1H data: {len(df_1h_clean)} candles")

            fig = plt.figure(figsize=(16, 10), facecolor='#1e222d')

            # 4H Chart (top)
            ax1 = plt.subplot(2, 1, 1)
            mpf.plot(
                df_4h_clean,
                type='candle',
                style=self.style,
                ax=ax1,
                volume=False,
                title=f'{symbol} - 4H Timeframe',
                ylabel='Price (USDT)',
            )

            # 1H Chart (bottom)
            ax2 = plt.subplot(2, 1, 2)
            mpf.plot(
                df_1h_clean,
                type='candle',
                style=self.style,
                ax=ax2,
                volume=True,
                title=f'{symbol} - 1H Timeframe',
                ylabel='Price (USDT)',
                ylabel_lower='Volume',
            )

            plt.tight_layout()

            # Save to buffer
            buffer = BytesIO()
            fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight', facecolor='#1e222d')
            buffer.seek(0)

            plt.close(fig)
            plt.close('all')
            gc.collect()

            return buffer

        except Exception as e:
            plt.close('all')
            raise Exception(f"Failed to generate comparison chart for {symbol}: {str(e)}")
