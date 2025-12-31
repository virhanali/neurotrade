package telegram

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"neurotrade/internal/domain"
)

type NotificationService struct {
	botToken   string
	chatID     string
	enabled    bool
	location   *time.Location
	httpClient *http.Client
}

type telegramMessage struct {
	ChatID    string `json:"chat_id"`
	Text      string `json:"text"`
	ParseMode string `json:"parse_mode"`
}

func NewNotificationService(botToken, chatID string) *NotificationService {
	enabled := botToken != "" && chatID != ""

	// Load timezone from environment or default to Asia/Jakarta
	tz := os.Getenv("TZ")
	if tz == "" {
		tz = "Asia/Jakarta"
	}

	location, err := time.LoadLocation(tz)
	if err != nil {
		// Fallback to UTC if timezone loading fails
		location = time.UTC
	}

	return &NotificationService{
		botToken: botToken,
		chatID:   chatID,
		enabled:  enabled,
		location: location,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// SendSignal sends a new trading signal notification to Telegram
func (s *NotificationService) SendSignal(signal domain.Signal) error {
	if !s.enabled {
		return nil // Silently skip if Telegram is not configured
	}

	// Determine emoji based on type (LONG/SHORT)
	sideEmoji := "🟢"
	if signal.Type == "SHORT" {
		sideEmoji = "🔴"
	}

	// Format message with Markdown
	message := fmt.Sprintf(
		"🚀 *NEW TRADING SIGNAL*\n\n"+
			"%s *%s %s*\n"+
			"━━━━━━━━━━━━━━━━━\n"+
			"📊 Entry: `$%.4f`\n"+
			"🛑 Stop Loss: `$%.4f`\n"+
			"🎯 Take Profit: `$%.4f`\n"+
			"📈 Confidence: `%d%%`\n"+
			"🕒 Time: `%s`\n\n"+
			"💡 *Reasoning:*\n%s",
		sideEmoji,
		signal.Type,
		signal.Symbol,
		signal.EntryPrice,
		signal.SLPrice,
		signal.TPPrice,
		signal.Confidence,
		signal.CreatedAt.In(s.location).Format("2006-01-02 15:04:05"),
		signal.Reasoning,
	)

	return s.sendMessage(message)
}

// SendReview sends a signal review (WIN/LOSS) report to Telegram
func (s *NotificationService) SendReview(signal domain.Signal) error {
	if !s.enabled {
		return nil
	}

	// Determine emoji and status based on review result
	var statusEmoji, statusText string
	if signal.ReviewResult != nil {
		switch *signal.ReviewResult {
		case "WIN":
			statusEmoji = "✅"
			statusText = "WIN"
		case "LOSS":
			statusEmoji = "❌"
			statusText = "LOSS"
		case "FLOATING_WIN":
			statusEmoji = "🟢"
			statusText = "FLOATING WIN"
		case "FLOATING_LOSS":
			statusEmoji = "🔴"
			statusText = "FLOATING LOSS"
		case "FLOATING":
			statusEmoji = "⚖️"
			statusText = "FLOATING"
		default:
			statusEmoji = "⏳"
			statusText = *signal.ReviewResult
		}
	} else {
		statusEmoji = "⏳"
		statusText = "PENDING"
	}

	message := fmt.Sprintf(
		"%s *SIGNAL REVIEW: %s*\n\n"+
			"📊 Symbol: `%s`\n"+
			"📈 Type: `%s`\n"+
			"━━━━━━━━━━━━━━━━━\n"+
			"🔵 Entry: `$%.4f`\n"+
			"🛑 Stop Loss: `$%.4f`\n"+
			"🎯 Take Profit: `$%.4f`\n"+
			"📈 Confidence: `%d%%`\n"+
			"🕒 Generated: `%s`\n"+
			"🏁 Reviewed: `%s`",
		statusEmoji,
		statusText,
		signal.Symbol,
		signal.Type,
		signal.EntryPrice,
		signal.SLPrice,
		signal.TPPrice,
		signal.Confidence,
		signal.CreatedAt.In(s.location).Format("2006-01-02 15:04"),
		time.Now().In(s.location).Format("2006-01-02 15:04"),
	)

	return s.sendMessage(message)
}

// sendMessage sends a message to Telegram using the Bot API
func (s *NotificationService) sendMessage(text string) error {
	if !s.enabled {
		return nil
	}

	url := fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", s.botToken)

	payload := telegramMessage{
		ChatID:    s.chatID,
		Text:      text,
		ParseMode: "Markdown",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal telegram message: %w", err)
	}

	resp, err := s.httpClient.Post(url, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to send telegram message: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("telegram API error (status %d): %s", resp.StatusCode, string(body))
	}

	return nil
}
