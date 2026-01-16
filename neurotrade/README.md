# ⚛️ NeuroTrade Frontend

> **The Command Center for AI Trading**

This is the React-based frontend application for NeuroTrade, designed to provide comprehensive visibility and control over the autonomous trading system. It communicates with the Go backend via REST APIs.

## Key Features

### 1. Intelligent Trade Execution
The system now employs a hybrid execution strategy. Instead of simple market orders, it intelligently selects between Limit orders for reversals (sniper entries) and Market orders for momentum breakouts. This maximizes entry efficiency and captures better prices during volatility.

### 2. Advanced AI Analysis
Powered by DeepSeek V3 and Gemini Vision, the AI Brain Center digs deep into market structure. It doesn't just look at indicators; it analyzes visual patterns, volume anomalies, and whale movements to form a high-confidence thesis before any trade is proposed.

### 3. Real-Time Risk Management
Every trade is protected by dynamic robust stop-loss mechanisms derived from ATR (Average True Range). If market conditions change or Bitcoin shows weakness, the system proactively vetoes or adjusts positions to protect capital.

### 4. Professional Live Dashboard
Monitor your equity curve, active positions, and detailed trade history in real-time. The interface is designed for clarity, allowing you to switch between Simulation and Real Trading modes instantly without complex reconfiguration.

---

## 🛠️ Tech Stack

*   **Framework:** React 18
*   **Language:** TypeScript
*   **Build Tool:** Vite
*   **Styling:** TailwindCSS
*   **State Management:** TanStack Query (React Query)
*   **Icons:** Lucide React
*   **Data Fetching:** Axios

---

## 📂 Project Structure

```bash
src/
├── api/             # API client & endpoints definition
├── components/      # Reusable UI components
│   ├── common/      # Buttons, Inputs, Cards
│   ├── dashboard/   # Dashboard-specific widgets
│   └── layout/      # Sidebar, Header, Layout wrappers
├── hooks/           # Custom React hooks (useUser, usePositions)
├── pages/           # Main page views
│   ├── DashboardPage.tsx    # Main overview
│   ├── MLAnalyticsPage.tsx  # AI Brain Center
│   ├── PositionsPage.tsx    # Live & Pending positions
│   └── ...
├── types/           # TypeScript interface definitions
└── utils/           # Helper functions & formatting
```

---

## 🚀 Development

### Prerequisites
*   Node.js 18+
*   npm or yarn

### Setup

1.  **Install Dependencies:**
    ```bash
    npm install
    ```

2.  **Start Dev Server:**
    ```bash
    npm run dev
    ```
    The app will run at `http://localhost:5173`.

3.  **Build for Production:**
    ```bash
    npm run build
    ```
    Output will be in `dist/` folder.

---

## 🔗 Backend Integration

The frontend expects the Go backend to be available (proxy setup in `vite.config.ts` handles API requests to `/api`):

```typescript
// vite.config.ts defaults
proxy: {
  '/api': {
    target: 'http://localhost:8080',
    changeOrigin: true,
  }
}
```

Ensure your backend server is running on port **8080** (or update the config) for data to populate.

---

## 🎨 Design Philosophy

*   **Clarity:** Data should be easy to read at a glance.
*   **Speed:** Actions (approving trades, panic selling) must be instant.
*   **Transparency:** Always show the user *why* something is happening (Brain Center).
