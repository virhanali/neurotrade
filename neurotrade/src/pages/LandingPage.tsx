import { Link } from 'react-router-dom';

export const LandingPage = () => {
    return (
        <div className="font-[Outfit] bg-slate-950 text-slate-300 selection:bg-emerald-500/30 selection:text-emerald-400 min-h-screen">
            {/* Navbar */}
            <nav className="fixed w-full z-50 bg-slate-900/70 backdrop-blur-md border-b border-white/5 transition-all duration-300">
                <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-emerald-700 flex items-center justify-center shadow-lg shadow-emerald-900/50">
                            <i className="ri-brain-line text-white text-xl"></i>
                        </div>
                        <span className="text-xl font-bold text-white tracking-tight">NeuroTrade <span className="text-emerald-500">AI</span></span>
                    </div>

                    <div className="hidden md:flex items-center gap-8">
                        <a href="#features" className="text-sm font-medium hover:text-white transition-colors">Technology</a>
                        <a href="#whale-radar" className="text-sm font-medium hover:text-white transition-colors">Whale Radar</a>
                        <a href="#security" className="text-sm font-medium hover:text-white transition-colors">Security</a>
                    </div>

                    <div className="flex items-center gap-4">
                        <Link to="/login" className="text-sm font-medium hover:text-white transition-colors">Sign In</Link>
                        <Link to="/register" className="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold transition-all shadow-lg shadow-emerald-900/20 hover:shadow-emerald-900/40">
                            Get Started
                        </Link>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="relative pt-40 pb-20 lg:pt-52 lg:pb-32 overflow-hidden">
                {/* Background Glow */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-full max-w-7xl bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.15)_0%,rgba(15,23,42,0)_70%)] pointer-events-none"></div>

                <div className="max-w-7xl mx-auto px-6 relative z-10 text-center">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-8 animate-fade-in-up">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                        Beta Access
                    </div>

                    <h1 className="text-5xl lg:text-7xl font-extrabold text-white tracking-tight leading-tight mb-8">
                        The AI Hedge Fund <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">In Your Pocket</span>
                    </h1>

                    <p className="text-lg lg:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
                        Stop gambling. Start scalping with an institutional-grade hybrid AI engine.
                        Combining <span className="text-white font-medium">DeepSeek Logic</span>, <span className="text-white font-medium">Computer Vision</span>, and real-time <span className="text-white font-medium">Whale Liquidations</span>.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                        <Link to="/register" className="w-full sm:w-auto px-8 py-4 rounded-xl bg-white text-slate-900 font-bold hover:bg-slate-100 transition-all flex items-center justify-center gap-2 shadow-xl shadow-white/5">
                            Start Trading Free
                            <i className="ri-arrow-right-line"></i>
                        </Link>
                        <a href="#how-it-works" className="w-full sm:w-auto px-8 py-4 rounded-xl bg-slate-800/50 border border-slate-700 text-white font-semibold hover:bg-slate-800 transition-all flex items-center justify-center gap-2 backdrop-blur-sm">
                            <i className="ri-play-circle-line text-xl"></i>
                            See Logic in Action
                        </a>
                    </div>

                    {/* Stats Row */}
                    <div className="mt-20 grid grid-cols-2 md:grid-cols-4 gap-8 border-t border-white/5 pt-12">
                        <div>
                            <h3 className="text-3xl font-bold text-white">15s</h3>
                            <p className="text-slate-500 text-sm mt-1">Scan Cycle Speed</p>
                        </div>
                        <div>
                            <h3 className="text-3xl font-bold text-white">235B</h3>
                            <p className="text-slate-500 text-sm mt-1">Model Parameters</p>
                        </div>
                        <div>
                            <h3 className="text-3xl font-bold text-white">6+</h3>
                            <p className="text-slate-500 text-sm mt-1">Whale Data Sources</p>
                        </div>
                        <div>
                            <h3 className="text-3xl font-bold text-white">24/7</h3>
                            <p className="text-slate-500 text-sm mt-1">Auto-Bodyguard</p>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features Grid */}
            <section id="features" className="py-24 bg-slate-900/50 relative">
                <div className="max-w-7xl mx-auto px-6">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl lg:text-4xl font-bold text-white mb-4">Why Retail Traders Fail (And You Won't)</h2>
                        <p className="text-slate-400 max-w-2xl mx-auto">Most bots just use RSI. We allow an actual AI intelligence to "see" the chart and "reason" about market structure.</p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-8">
                        {/* Card 1 */}
                        <div className="p-8 rounded-2xl bg-slate-900 border border-slate-800/60 transition-all group hover:bg-gradient-to-br hover:from-slate-800 hover:to-slate-900 hover:border-emerald-500/30 hover:-translate-y-1">
                            <div className="w-14 h-14 rounded-lg bg-blue-500/10 flex items-center justify-center mb-6 group-hover:bg-blue-500/20 transition-colors">
                                <i className="ri-brain-line text-blue-400 text-2xl"></i>
                            </div>
                            <h3 className="text-xl font-bold text-white mb-3">Hybrid AI Intelligence</h3>
                            <p className="text-slate-400 leading-relaxed text-sm">
                                Combining <strong>DeepSeek V3</strong> for logical reasoning and <strong>Qwen3 Vision</strong> to chart patterns like a pro trader. Identifies Falling Knives vs. True Reversals.
                            </p>
                        </div>

                        {/* Card 2 */}
                        <div className="p-8 rounded-2xl bg-slate-900 border border-slate-800/60 transition-all group hover:bg-gradient-to-br hover:from-slate-800 hover:to-slate-900 hover:border-emerald-500/30 hover:-translate-y-1">
                            <div className="w-14 h-14 rounded-lg bg-purple-500/10 flex items-center justify-center mb-6 group-hover:bg-purple-500/20 transition-colors">
                                <i className="ri-radar-fill text-purple-400 text-2xl"></i>
                            </div>
                            <h3 className="text-xl font-bold text-white mb-3">Whale Radar</h3>
                            <p className="text-slate-400 leading-relaxed text-sm">
                                Don't fight the ocean. We track <strong>real-time liquidations</strong>, order book imbalances, and institutional buy walls to predict Pumps & Dumps before they happen.
                            </p>
                        </div>

                        {/* Card 3 */}
                        <div className="p-8 rounded-2xl bg-slate-900 border border-slate-800/60 transition-all group hover:bg-gradient-to-br hover:from-slate-800 hover:to-slate-900 hover:border-emerald-500/30 hover:-translate-y-1">
                            <div className="w-14 h-14 rounded-lg bg-emerald-500/10 flex items-center justify-center mb-6 group-hover:bg-emerald-500/20 transition-colors">
                                <i className="ri-shield-check-fill text-emerald-400 text-2xl"></i>
                            </div>
                            <h3 className="text-xl font-bold text-white mb-3">Self-Learning Bodyguard</h3>
                            <p className="text-slate-400 leading-relaxed text-sm">
                                The system <strong>learns from every trade</strong>. Using LightGBM, it adapts confidence thresholds based on real-time win rates and market regimes (Trending/Ranging).
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* UI Showcase */}
            <section className="py-24 relative overflow-hidden">
                <div className="max-w-7xl mx-auto px-6 text-center">
                    <h2 className="text-3xl lg:text-4xl font-bold text-white mb-16">Designed for Command & Control</h2>

                    <div className="relative rounded-2xl border border-slate-800 shadow-2xl shadow-emerald-500/10 overflow-hidden bg-slate-900 max-w-5xl mx-auto">
                        <div className="absolute top-0 w-full h-12 bg-slate-800/50 border-b border-white/5 flex items-center px-4 gap-2 z-10">
                            <div className="w-3 h-3 rounded-full bg-rose-500"></div>
                            <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                            <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
                        </div>
                        {/* Use App Screenshot if available, fallback to placeholder */}
                        <div className="bg-slate-950 pt-12 relative group">
                            <img
                                src="/assets/dashboard-mockup.png"
                                onError={(e) => {
                                    e.currentTarget.src = 'https://placehold.co/1200x675/0f172a/1e293b?text=NeuroTrade+Dashboard+Preview&font=montserrat';
                                }}
                                alt="Dashboard Interface"
                                className="w-full h-auto opacity-90 group-hover:opacity-100 transition-opacity"
                            />
                            <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
                                <Link to="/register" className="px-8 py-3 bg-emerald-600 text-white font-bold rounded-lg transform scale-90 group-hover:scale-100 transition-transform">
                                    Try Demo Live
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-32 relative">
                <div className="max-w-4xl mx-auto px-6 text-center">
                    <h2 className="text-4xl lg:text-5xl font-extrabold text-white mb-6 tracking-tight">Ready to Automate Your Alpha?</h2>
                    <p className="text-xl text-slate-400 mb-10">Join the closed beta of the most advanced retail trading system ever built.</p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                        <Link to="/register" className="w-full sm:w-auto px-8 py-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition-all shadow-lg shadow-emerald-900/40 text-lg">
                            Create Free Account
                        </Link>
                    </div>
                    <p className="mt-6 text-sm text-slate-500">No credit card required. Paper trading mode active by default.</p>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-white/5 py-12 bg-slate-950">
                <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center">
                            <i className="ri-brain-line text-white"></i>
                        </div>
                        <span className="text-lg font-bold text-white">NeuroTrade AI</span>
                    </div>
                    <div className="text-slate-500 text-sm">
                        &copy; {new Date().getFullYear()} NeuroTrade Inc. All rights reserved.
                    </div>
                    <div className="flex gap-6">
                        <a href="#" className="text-slate-500 hover:text-white transition-colors"><i className="ri-twitter-x-line text-xl"></i></a>
                        <a href="#" className="text-slate-500 hover:text-white transition-colors"><i className="ri-github-fill text-xl"></i></a>
                        <a href="#" className="text-slate-500 hover:text-white transition-colors"><i className="ri-telegram-fill text-xl"></i></a>
                    </div>
                </div>
            </footer>
        </div>
    );
};
