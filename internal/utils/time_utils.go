package utils

import (
	"time"
)

var jakartaLoc *time.Location

func init() {
	var err error
	jakartaLoc, err = time.LoadLocation("Asia/Jakarta")
	if err != nil {
		// Fallback to Local if timezone data is missing
		// In production docker, ensure tzdata is installed
		jakartaLoc = time.Local
	}
}

// GetJakartaTime returns current time in Jakarta timezone
func GetJakartaTime() time.Time {
	return time.Now().In(jakartaLoc)
}

// GetStartOfDay returns 00:00:00 of the given time in Jakarta timezone
func GetStartOfDay() time.Time {
	now := GetJakartaTime()
	return time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, jakartaLoc)
}

// GetLocation returns the Jakarta *time.Location
func GetLocation() *time.Location {
	return jakartaLoc
}
