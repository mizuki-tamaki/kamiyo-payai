# Deployment Guide - x402 Payment Gateway

Complete production deployment guide for the x402 Payment Gateway.

## Prerequisites

- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+
- Python 3.11+
- Domain with SSL certificate

## Quick Start (Development)

```bash
# 1. Clone and setup
git clone https://github.com/mizuki-tamaki/kamiyo-payai.git
cd kamiyo-payai

# 2. Configure environment
cp .env.example .env
# Edit .env with your values

# 3. Start services with Docker Compose
docker-compose up -d

# 4. Run migrations
docker-compose exec x402-api alembic upgrade head

# 5. Access services
# API: http://localhost:8000
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
# Flower: http://localhost:5555
```

## Production Deployment

### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Security Configuration

**CRITICAL: Update default credentials in .env**

```bash
# Generate secure keys
openssl rand -hex 32  # For JWT_SECRET_KEY
openssl rand -hex 32  # For X402_ADMIN_KEY

# Update .env
X402_ADMIN_KEY=<generated-key>
JWT_SECRET_KEY=<generated-key>
X402_PAYAI_MERCHANT_ADDRESS=<your-actual-address>
```

**Configure firewall:**

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 3. Database Setup

```bash
# Create production database
createdb kamiyo

# Run migrations
alembic upgrade head

# Create database backup script
cat > /usr/local/bin/backup-x402-db.sh <<'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/x402"
mkdir -p $BACKUP_DIR
pg_dump kamiyo | gzip > "$BACKUP_DIR/kamiyo_$(date +%Y%m%d_%H%M%S).sql.gz"
find $BACKUP_DIR -mtime +7 -delete
EOF

chmod +x /usr/local/bin/backup-x402-db.sh

# Add to crontab
echo "0 2 * * * /usr/local/bin/backup-x402-db.sh" | crontab -
```

### 4. SSL/TLS Setup

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

### 5. Nginx Configuration

```nginx
# /etc/nginx/sites-available/x402-payment-gateway
upstream x402_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    location / {
        proxy_pass http://x402_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /metrics {
        deny all;  # Restrict metrics endpoint
    }
}
```

### 6. Start Production Services

```bash
# Build and start
docker-compose -f docker-compose.yml up -d --build

# Verify services are running
docker-compose ps

# Check logs
docker-compose logs -f x402-api
```

### 7. Monitoring Setup

**Grafana Dashboard Import:**

1. Access Grafana at https://your-domain.com:3000
2. Login (change default password!)
3. Import dashboard from `monitoring/grafana/dashboards/`

**Alert Configuration:**

```yaml
# Add to prometheus.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

rule_files:
  - "alerts.yml"
```

### 8. Health Checks

```bash
# API health
curl https://your-domain.com/health

# Database connectivity
docker-compose exec postgres pg_isready

# Redis connectivity
docker-compose exec redis redis-cli ping

# Celery workers
docker-compose exec celery-worker celery -A api.x402.tasks inspect active
```

## Kubernetes Deployment (Optional)

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: x402-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: x402-api
  template:
    metadata:
      labels:
        app: x402-api
    spec:
      containers:
      - name: x402-api
        image: x402-payment-gateway:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: x402-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: x402-secrets
              key: redis-url
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Monitoring & Maintenance

### Daily Checks

```bash
# Check service status
docker-compose ps

# View recent logs
docker-compose logs --tail=100 x402-api

# Check disk usage
df -h

# Check database size
docker-compose exec postgres psql -U postgres -d kamiyo -c "SELECT pg_size_pretty(pg_database_size('kamiyo'));"
```

### Weekly Maintenance

```bash
# Update Docker images
docker-compose pull
docker-compose up -d

# Vacuum database
docker-compose exec postgres psql -U postgres -d kamiyo -c "VACUUM ANALYZE;"

# Clear old Redis data
docker-compose exec redis redis-cli FLUSHDB
```

### Backup & Recovery

**Backup:**
```bash
# Database
pg_dump kamiyo > backup.sql

# Redis
redis-cli --rdb /backup/dump.rdb

# Configuration
tar -czf config-backup.tar.gz .env docker-compose.yml
```

**Recovery:**
```bash
# Restore database
psql kamiyo < backup.sql

# Restore Redis
redis-cli --rdb /backup/dump.rdb
```

## Scaling

### Horizontal Scaling

```bash
# Scale API workers
docker-compose up -d --scale x402-api=5

# Scale Celery workers
docker-compose up -d --scale celery-worker=3
```

### Vertical Scaling

Update `docker-compose.yml`:
```yaml
services:
  x402-api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

## Troubleshooting

### API Not Responding

```bash
# Check if container is running
docker-compose ps x402-api

# Check logs
docker-compose logs x402-api

# Restart service
docker-compose restart x402-api
```

### Database Connection Issues

```bash
# Check database logs
docker-compose logs postgres

# Test connection
docker-compose exec x402-api python -c "from api.database import engine; print(engine.url)"
```

### High Memory Usage

```bash
# Check container stats
docker stats

# Analyze memory usage
docker-compose exec x402-api ps aux --sort=-%mem | head
```

## Performance Optimization

### Database Optimization

```sql
-- Create indexes for common queries
CREATE INDEX idx_x402_payments_created_at_status
ON x402_payments(created_at, status);

CREATE INDEX idx_x402_usage_payment_endpoint
ON x402_usage(payment_id, endpoint);
```

### Redis Optimization

```bash
# Set maxmemory policy
redis-cli CONFIG SET maxmemory-policy allkeys-lru
redis-cli CONFIG SET maxmemory 2gb
```

### Application Tuning

```bash
# Increase worker pool
WORKERS=8 docker-compose up -d x402-api

# Tune Gunicorn
gunicorn api.main:app \
  -w 8 \
  -k uvicorn.workers.UvicornWorker \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --timeout 60
```

## Security Hardening Checklist

- [ ] Change all default passwords
- [ ] Configure firewall (UFW/iptables)
- [ ] Enable SSL/TLS
- [ ] Restrict database access
- [ ] Set up fail2ban
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Monitor security alerts
- [ ] Backup encryption
- [ ] API rate limiting

## Support

For issues or questions:
- GitHub Issues: https://github.com/mizuki-tamaki/kamiyo-payai/issues
- Email: dev@kamiyo.ai
- Security: security@kamiyo.ai
