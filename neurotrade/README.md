# ⚛️ NeuroTrade Frontend

> **The Command Center for AI Trading**

This is the React-based frontend application for NeuroTrade, designed to provide comprehensive visibility and control over the autonomous trading system. It communicates with the Go backend via REST APIs.

## 🖥️ key Features

### 1. **Live Trading Dashboard**
*   **Real-time PnL:** Watch your equity grow (or shrink) in real-time.
*   **Active Positions:** Monitor open trades with live price updates and dynamic PnL coloring.
*   **Mode Switcher:** Seamlessly toggle between **REAL** (Live Money) and **PAPER** (Simulation) modes with a single click.

### 2. **AI Brain Center (Analytics)**
*   **Deep Insights:** Visualize *why* the AI took a trade.
*   **Confidence Heatmaps:** See the distribution of AI confidence levels.
*   **Whale Radar:** Track institutional signals acting in the market.
*   **Market Hours Analysis:** Understand which hours yield the best trading opportunities.

### 3. **Trade History**
*   **Performance Tracking:** Detailed log of past trades including profit/loss, fees, and duration.
*   **Outcome Analysis:** See how simulated "learning" trades would have performed.

### 4. **Modern UX/UI**
*   **Dark Mode First:** Sleek, professional dark theme designed for long trading sessions.
*   **Responsive:** Fully optimized for Mobile, Tablet, and Desktop.
*   **Fast:** Built with **Vite** for lightning-fast loading and HMR.

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
