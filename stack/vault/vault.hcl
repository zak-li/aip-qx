ui = true
disable_mlock = true

storage "raft" {
  path    = "/opt/vault/data"
  node_id = "rwa-vault-node-1"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

api_addr     = "http://10.10.10.150:8200"
cluster_addr = "http://10.10.10.150:8201"
