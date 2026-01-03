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

    def generate_chart_image(self, df: pd.DataFrame, symbol: str) -> BytesIO:
        """
        Generate candlestick chart with Bollinger Bands and Volume

        Args:
            df: DataFrame with OHLCV data (must have datetime index)
            symbol: Trading pair name for title

        Returns:
            BytesIO buffer containing PNG image
        """
        try:
            # Calculate Bollinger Bands
            rolling_mean = df['close'].rolling(window=20).mean()
            rolling_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = rolling_mean + (rolling_std * 2)
            df['bb_middle'] = rolling_mean
            df['bb_lower'] = rolling_mean - (rolling_std * 2)

            # Add plots for Bollinger Bands
            add_plots = [
                mpf.make_addplot(df['bb_upper'], color='#787b86', linestyle='--', width=0.7),
                mpf.make_addplot(df['bb_middle'], color='#2962ff', linestyle='-', width=1),
                mpf.make_addplot(df['bb_lower'], color='#787b86', linestyle='--', width=0.7),
            ]

            # Add EMA if available
            if 'ema_50' in df.columns and not df['ema_50'].isna().all():
                add_plots.append(
                    mpf.make_addplot(df['ema_50'], color='#ff6d00', linestyle='-', width=1.5)
                )

            if 'ema_200' in df.columns and not df['ema_200'].isna().all():
                add_plots.append(
                    mpf.make_addplot(df['ema_200'], color='#00bcd4', linestyle='-', width=1.5)
                )

            # Create figure
            fig, axes = mpf.plot(
                df,
                type='candle',
                style=self.style,
                volume=True,
                addplot=add_plots,
                title=f'{symbol} - 1H Chart',
                ylabel='Price (USDT)',
                ylabel_lower='Volume',
                figsize=(12, 8),
                returnfig=True,
                warn_too_much_data=200,
            )

            # Save to buffer
            buffer = BytesIO()
            fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight', facecolor='#1e222d')
            buffer.seek(0)

            # Close figure and clear memory aggressively
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
            fig = plt.figure(figsize=(16, 10), facecolor='#1e222d')

            # 4H Chart (top)
            ax1 = plt.subplot(2, 1, 1)
            mpf.plot(
                df_4h.tail(50),
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
                df_1h.tail(100),
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
