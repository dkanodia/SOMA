#!/bin/bash
redis-cli set corp:employee_count 847
redis-cli set corp:api_key "sk-prod-8f3a2c1d9e7b4f6a"
redis-cli set corp:db_password "Pr0d_DB_Pass_2024!"
redis-cli set corp:jwt_secret "super_secret_jwt_key_do_not_share"
redis-cli set corp:ceo_email "j.hartwell@acmecorp.internal"
redis-cli set corp:payroll_total "4823000"
redis-cli lpush corp:recent_logins "alice" "bob" "charlie" "diana" "evan" "soma"
redis-cli set corp:stripe_key "sk_live_exampleKeyHere9876543210"
redis-cli set corp:aws_key "AKIAIOSFODNN7EXAMPLE"
redis-cli set corp:aws_secret "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
redis-cli set session:admin_token "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW4ifQ.example"
echo "[redis] Seed data loaded"
