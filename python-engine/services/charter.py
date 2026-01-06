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
            # Early validation - check if df is valid
            if df is None or len(df) == 0:
                raise Exception(f"Empty DataFrame received")

            # Focus on recent data (last 60 candles)
            plot_df = df.tail(60).copy() if len(df) > 60 else df.copy()

            # VALIDATION: Check required columns exist
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in plot_df.columns]
            if missing_cols:
                raise Exception(f"Missing required columns: {missing_cols}")

            # CRITICAL FIX: Drop rows with NaN in OHLCV columns BEFORE any processing
            plot_df = plot_df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])

            # VALIDATION: Check if we have enough clean data after dropping NaN
            if len(plot_df) < 2:
                raise Exception(f"Insufficient clean data: {len(plot_df)} valid candles (need at least 2)")

            # Reset index to ensure continuous DatetimeIndex for mplfinance
            plot_df = plot_df.reset_index(drop=False)
            if 'timestamp' in plot_df.columns:
                plot_df = plot_df.set_index('timestamp')
            elif 'index' in plot_df.columns:
                plot_df = plot_df.set_index('index')

            # 2. STRUCTURE - Support/Resistance levels (safe after dropna)
            recent_low = float(plot_df['low'].min())
            recent_high = float(plot_df['high'].max())

            # Build addplots - only add if data is valid
            add_plots = []

            # Volume Climax Detection (optional - skip if fails)
            try:
                vol_ma = plot_df['volume'].rolling(window=min(20, len(plot_df))).mean()
                vol_ma = vol_ma.fillna(plot_df['volume'])
                is_climax = plot_df['volume'] > (vol_ma * 2.5)
                if is_climax.any():
                    climax_signals = plot_df['low'].where(is_climax) * 0.995
                    add_plots.append(
                        mpf.make_addplot(climax_signals, type='scatter', markersize=40, marker='^', color='#ffd700', panel=0)
                    )
            except Exception:
                pass  # Skip climax signals if calculation fails

            # Bollinger Bands (only if columns exist AND have valid data)
            if all(col in plot_df.columns for col in ['bb_upper', 'bb_middle', 'bb_lower']):
                try:
                    # Only add if at least 50% of values are valid
                    if plot_df['bb_upper'].notna().sum() > len(plot_df) * 0.5:
                        bb_upper = plot_df['bb_upper'].ffill().bfill()
                        bb_middle = plot_df['bb_middle'].ffill().bfill()
                        bb_lower = plot_df['bb_lower'].ffill().bfill()
                        add_plots.extend([
                            mpf.make_addplot(bb_upper, color='#787b86', linestyle='--', width=0.8),
                            mpf.make_addplot(bb_middle, color='#2962ff', linestyle='-', width=1.0),
                            mpf.make_addplot(bb_lower, color='#787b86', linestyle='--', width=0.8),
                        ])
                except Exception:
                    pass  # Skip BB if any issue

            # EMAs (only if columns exist AND have valid data)
            if 'ema_50' in plot_df.columns and plot_df['ema_50'].notna().sum() > len(plot_df) * 0.5:
                try:
                    ema_50 = plot_df['ema_50'].ffill().bfill()
                    add_plots.append(mpf.make_addplot(ema_50, color='#ff6d00', linestyle='-', width=1.2))
                except Exception:
                    pass
            if 'ema_200' in plot_df.columns and plot_df['ema_200'].notna().sum() > len(plot_df) * 0.5:
                try:
                    ema_200 = plot_df['ema_200'].ffill().bfill()
                    add_plots.append(mpf.make_addplot(ema_200, color='#00bcd4', linestyle='-', width=1.5))
                except Exception:
                    pass

            # Horizontal Lines for S/R
            hlines = dict(hlines=[recent_low, recent_high], colors=['#4caf50', '#f44336'], linestyle=':', linewidths=0.8, alpha=0.6)

            # Create figure - use minimal addplots if list is empty
            plot_kwargs = {
                'type': 'candle',
                'style': self.style,
                'volume': True,
                'hlines': hlines,
                'title': f'{symbol} - {interval} (Smart Money View)',
                'ylabel': 'Price',
                'ylabel_lower': 'Vol',
                'figsize': (12, 8),
                'returnfig': True,
                'warn_too_much_data': 200,
                'tight_layout': True
            }
            if add_plots:
                plot_kwargs['addplot'] = add_plots

            fig, axes = mpf.plot(plot_df, **plot_kwargs)

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
