FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY src/ ./src/
RUN CGO_ENABLED=0 GOOS=linux go build -o status-service ./src/...

FROM gcr.io/distroless/static-debian12
WORKDIR /app
COPY --from=builder /app/status-service ./
COPY openapi.yaml ./
USER nonroot:nonroot
EXPOSE 3003
CMD ["./status-service"]
