# How to setup this repository?

Để chạy được DeerFlow Agent thì sẽ cần phải thực hiện các bước sau.

## Requirements

- Tạo một AWS CLI Profile ở trong máy trước, đặt tên khác `default` (trong config để mặc định là `ecv`).
- Đảm bảo máy đã cài sẵn Docker.

## Steps

### Step 1: Create app config

Chạy lệnh sau để tạo các file config từ template:

```bash
make config
```

Lệnh này sẽ tạo `config.yaml`, `.env`, và `frontend/.env` từ các file example tương ứng.

### Step 2: Configure model

Sửa `config.yaml`, phần `models`. Ví dụ với Bedrock:

```yaml
models:
  - name: claude-4-5-sonnet
    display_name: Claude 4.5 Sonnet
    use: langchain_aws:ChatBedrockConverse
    model: global.anthropic.claude-sonnet-4-5-20250929-v1:0
    credentials_profile_name: ecv          # Tên AWS CLI profile (KHÔNG phải aws_profile)
    region_name: ap-southeast-1            # Bắt buộc phải có
    max_tokens: 8192
```

> **Lưu ý:** Param đúng là `credentials_profile_name`, không phải `aws_profile`. Và phải có `region_name` dù profile đã config region.

### Step 3: Start app

```bash
# Pull sandbox image (chỉ cần chạy 1 lần)
make docker-init

# Start services
make docker-start
```

Truy cập: http://localhost:2026

### Quản lý container

```bash
# Dừng tạm thời (giữ container)
docker compose -f docker/docker-compose-dev.yaml stop

# Chạy lại
docker compose -f docker/docker-compose-dev.yaml start

# Dừng + xóa container, network, volume, image (làm lại từ đầu)
docker compose -f docker/docker-compose-dev.yaml down -v --rmi all

# Rebuild khi đổi Dockerfile hoặc dependencies
docker compose -f docker/docker-compose-dev.yaml up -d --build
```

## Troubleshooting

### 502 Bad Gateway

- Check log: `docker exec deer-flow-langgraph cat /app/logs/langgraph.log | tail -30`
- Nếu lỗi YAML parse → sửa `config.yaml` (thường thiếu `#` ở comment)
- Sau khi recreate container, nhớ restart nginx để refresh DNS: `docker compose -f docker/docker-compose-dev.yaml restart nginx`

### Hot-reload

Không cần remove container mỗi khi đổi code. Cả frontend, gateway, và langgraph đều có hot-reload. Chỉ cần rebuild (`up --build`) khi thay đổi `Dockerfile` hoặc dependencies.
