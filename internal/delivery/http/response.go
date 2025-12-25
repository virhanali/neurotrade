package http

import (
	"net/http"

	"github.com/labstack/echo/v4"
)

// Response represents a standardized API response
type Response struct {
	Status  string      `json:"status"`
	Message string      `json:"message,omitempty"`
	Data    interface{} `json:"data,omitempty"`
	Error   interface{} `json:"error,omitempty"`
}

// SuccessResponse sends a success response
func SuccessResponse(c echo.Context, data interface{}) error {
	return c.JSON(http.StatusOK, Response{
		Status: "success",
		Data:   data,
	})
}

// SuccessMessageResponse sends a success response with a message
func SuccessMessageResponse(c echo.Context, message string, data interface{}) error {
	return c.JSON(http.StatusOK, Response{
		Status:  "success",
		Message: message,
		Data:    data,
	})
}

// CreatedResponse sends a 201 Created response
func CreatedResponse(c echo.Context, data interface{}) error {
	return c.JSON(http.StatusCreated, Response{
		Status: "success",
		Data:   data,
	})
}

// ErrorResponse sends an error response
func ErrorResponse(c echo.Context, statusCode int, message string, err interface{}) error {
	return c.JSON(statusCode, Response{
		Status:  "error",
		Message: message,
		Error:   err,
	})
}

// BadRequestResponse sends a 400 Bad Request response
func BadRequestResponse(c echo.Context, message string) error {
	return ErrorResponse(c, http.StatusBadRequest, message, nil)
}

// UnauthorizedResponse sends a 401 Unauthorized response
func UnauthorizedResponse(c echo.Context, message string) error {
	return ErrorResponse(c, http.StatusUnauthorized, message, nil)
}

// ForbiddenResponse sends a 403 Forbidden response
func ForbiddenResponse(c echo.Context, message string) error {
	return ErrorResponse(c, http.StatusForbidden, message, nil)
}

// NotFoundResponse sends a 404 Not Found response
func NotFoundResponse(c echo.Context, message string) error {
	return ErrorResponse(c, http.StatusNotFound, message, nil)
}

// InternalServerErrorResponse sends a 500 Internal Server Error response
func InternalServerErrorResponse(c echo.Context, message string, err error) error {
	errMsg := ""
	if err != nil {
		errMsg = err.Error()
	}
	return ErrorResponse(c, http.StatusInternalServerError, message, errMsg)
}
