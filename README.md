# Document Intelligence Copilot

Plataforma de processamento inteligente de documentos que transforma arquivos não estruturados (PDFs, imagens, documentos escaneados) em dados estruturados, insights acionáveis e alertas operacionais.

## Stack

- **Frontend:** Streamlit (multi-page app)
- **AI:** Amazon Bedrock (Claude Sonnet — classificação, extração, insights)
- **Database:** DynamoDB (Documents, Extractions, Insights, HumanReviews)
- **Storage:** Amazon S3
- **Deploy:** EC2 Ubuntu (CloudFormation)

## Desenvolvimento Local

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais AWS

# Rodar aplicação
streamlit run app.py

# Testes
pytest
pytest --cov
```

## Deploy AWS (EC2 Demo)

A infraestrutura é definida via CloudFormation em `infrastructure/cloudformation.yaml`.

### Arquitetura

```
Internet → EC2 (port 8501) → Bedrock / DynamoDB / S3
              │
              └── Public Subnet (acesso direto via IP público)
```

### Recursos Provisionados

| Recurso | Descrição |
|---------|-----------|
| VPC | 10.1.0.0/16 com 1 subnet pública |
| S3 Bucket | Armazenamento de documentos |
| DynamoDB | 4 tabelas (Documents, Extractions, Insights, HumanReviews) |
| EC2 Instance | Ubuntu com Streamlit (systemd service) |
| IAM Role | EC2 role com acesso a S3, DynamoDB, Bedrock, CloudWatch |
| Security Group | SSH (22) + Streamlit (8501) abertos |

### Parâmetros do Template

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `KeyPairName` | *(obrigatório)* | Key pair SSH para acesso EC2 |
| `InstanceType` | `t3.small` | Tipo da instância (t3.micro/small/medium) |
| `BedrockModelId` | `us.anthropic.claude-sonnet-4-6` | Modelo Bedrock |

### Passos para Deploy

```bash
# 1. Deploy do CloudFormation stack
aws cloudformation deploy \
  --template-file infrastructure/cloudformation.yaml \
  --stack-name doc-intel-copilot \
  --parameter-overrides \
    KeyPairName=<YOUR_KEY_PAIR_NAME> \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Obter URL da aplicação
aws cloudformation describe-stacks \
  --stack-name doc-intel-copilot \
  --query 'Stacks[0].Outputs[?OutputKey==`AppURL`].OutputValue' \
  --output text
```

### Outputs do Stack

| Output | Descrição |
|--------|-----------|
| `AppURL` | URL da aplicação Streamlit (http://IP:8501) |
| `EC2PublicIP` | IP público da instância EC2 |
| `S3Bucket` | Nome do bucket S3 |
| `SSHCommand` | Comando SSH para acesso à instância |

## Pipeline de Processamento

```
Upload (PDF/imagem) → Classificação IA (categoria + confiança)
                    → Extração Estruturada (campos JSON por categoria)
                    → Geração de Insights (alertas + inconsistências)
                    → Revisão Humana (aprovar/corrigir/rejeitar)
```

## Testes

```bash
pytest                  # Unit + property-based tests
pytest --cov            # Com cobertura
pytest tests/integration/  # Testes de integração (moto)
```

Todos os serviços AWS são mockados com `moto` nos testes — nenhum recurso real é necessário.
