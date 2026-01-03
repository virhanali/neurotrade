package dto

// SignalViewModel represents the data structure for the signal list template
type SignalViewModel struct {
	Symbol          string
	Type            string // SHORT/LONG
	SideBg          string // Tailwind classes
	Confidence      int
	ConfidenceColor string
	Timestamp       string // HH:mm
	IsRunning       bool
	Res             string // WIN/LOSS
	ResColor        string
	PnlVal          float64
	PnlDollar       float64
}
