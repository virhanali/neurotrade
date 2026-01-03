package dto

// ToggleModeRequest represents the toggle mode request
type ToggleModeRequest struct {
	Mode string `json:"mode"` // "PAPER" or "REAL"
}

// PositionOutput represents a position in API responses
type PositionOutput struct {
	ID         string   `json:"id"`
	Symbol     string   `json:"symbol"`
	Side       string   `json:"side"`
	EntryPrice float64  `json:"entry_price"`
	SLPrice    float64  `json:"sl_price"`
	TPPrice    float64  `json:"tp_price"`
	Size       float64  `json:"size"`
	ExitPrice  *float64 `json:"exit_price,omitempty"`
	PnL        *float64 `json:"pnl,omitempty"`
	Status     string   `json:"status"`
	CreatedAt  string   `json:"created_at"`
	ClosedAt   *string  `json:"closed_at,omitempty"`
}

// UserOutput represents user details in API responses
type UserOutput struct {
	ID           string  `json:"id"`
	Username     string  `json:"username"`
	Role         string  `json:"role"`
	Mode         string  `json:"mode"`
	PaperBalance float64 `json:"paper_balance"`
}
