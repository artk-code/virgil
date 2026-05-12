# ------------------------------------------------------------------------------
# Go API — cached module layer, static binary, non-root runtime.
# ------------------------------------------------------------------------------
FROM golang:1.22-alpine AS builder
RUN apk add --no-cache git ca-certificates
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/api .

FROM alpine:3.19
RUN apk add --no-cache ca-certificates curl tini \
 && addgroup -S app && adduser -S -G app app
COPY --from=builder /out/api /usr/local/bin/api
USER app
EXPOSE 8080
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/usr/local/bin/api"]
