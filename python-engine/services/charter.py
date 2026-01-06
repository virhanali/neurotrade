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

            # VALIDATION: Check if we have enough data
            if len(plot_df) < 2:
                raise Exception(f"Insufficient data for chart generation: {len(plot_df)} candles (need at least 2)")

            if 'low' not in plot_df.columns or 'high' not in plot_df.columns or 'volume' not in plot_df.columns:
                raise Exception("Missing required columns: low, high, volume")

            # 1. VOLUME CLIMAX LOGIC
            # Calculate Volume MA
            vol_ma = plot_df['volume'].rolling(window=20).mean()

            # Define Volume Colors based on Relative Volume (RVOL)
            # Default: Grey (Noise)
            # High (>1.5x): Cyan (Activity)
            # Climax (>2.5x): Yellow (Smart Money / Stopping Volume)
            vol_colors = []
            for i in range(len(plot_df)):
                vol = plot_df['volume'].iloc[i]
                avg = vol_ma.iloc[i] if pd.notna(vol_ma.iloc[i]) else vol

                if vol > 2.5 * avg:
                    vol_colors.append('#ffd700')  # GOLD for Climax
                elif vol > 1.5 * avg:
                    vol_colors.append('#00e5ff')  # CYAN for High Activity
                else:
                    vol_colors.append('#363a45')  # GREY for Normal

            # 2. STRUCTURE (Simulated Support/Resistance)
            # Find recent significant Swing High/Low in the visible window
            # Safe extraction (guaranteed to have data after validation above)
            recent_low = plot_df['low'].min()
            recent_high = plot_df['high'].max()
            
            add_plots = []
            
            # Add Volume Climax Overlay (We need to use 'volume' kwarg in plot, but we can pass colors)
            # Actually, mpf handles volume colors via marketcolors, but that's global.
            # To have specific bar colors, we might need a workaround or accept global styling.
            # Workaround: We will use the 'volume' argument in mpf.plot and pass `volume_panel=1`. 
            # MPF doesn't easily support per-bar volume colors without custom overrides. 
            # SIMPLER ALTERNATIVE: We plot dots on the price chart to signal volume climax.
            
            # Add "Smart Money" Signal Dots on Price
            # Yellow Dot below candle = Climax Volume (Attention!)
            climax_signals = [plot_df['low'].iloc[i] * 0.995 if plot_df['volume'].iloc[i] > 2.5 * vol_ma.iloc[i] else float('nan') for i in range(len(plot_df))]
            
            add_plots.append(
                 mpf.make_addplot(climax_signals, type='scatter', markersize=40, marker='^', color='#ffd700', panel=0)
            )

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
