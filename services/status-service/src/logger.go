package main

import (
	"encoding/json"
	"os"
)

// Minimal leveled JSON logger, matching the shape used by the other RPD 311
// services. Raccoon City house tone in messages; enum values and codes verbatim.
var logLevels = map[string]int{"error": 0, "warn": 1, "info": 2, "debug": 3}

type Logger struct {
	threshold int
}

func NewLogger(level string) *Logger {
	t, ok := logLevels[level]
	if !ok {
		t = logLevels["info"]
	}
	return &Logger{threshold: t}
}

func (l *Logger) emit(level, message string, meta map[string]any) {
	if logLevels[level] > l.threshold {
		return
	}
	line := map[string]any{"level": level, "service": "status-service", "message": message}
	if len(meta) > 0 {
		line["meta"] = meta
	}
	enc := json.NewEncoder(os.Stdout)
	if level == "error" {
		enc = json.NewEncoder(os.Stderr)
	}
	_ = enc.Encode(line)
}

func (l *Logger) Error(message string, meta map[string]any) { l.emit("error", message, meta) }
func (l *Logger) Warn(message string, meta map[string]any)  { l.emit("warn", message, meta) }
func (l *Logger) Info(message string, meta map[string]any)  { l.emit("info", message, meta) }
func (l *Logger) Debug(message string, meta map[string]any) { l.emit("debug", message, meta) }
