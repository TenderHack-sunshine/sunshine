FROM golang:1.22-alpine AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY backend ./backend

FROM build AS api-build
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /assistant-api ./backend/cmd/api

FROM build AS migrate-build
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /migrate ./backend/cmd/migrate

FROM build AS api

COPY --from=api-build /assistant-api /assistant-api
EXPOSE 8080
USER 65532:65532
ENTRYPOINT ["/assistant-api"]

FROM build AS migrate
COPY --from=migrate-build /migrate /migrate
USER 65532:65532
ENTRYPOINT ["/migrate"]
