path "rwa-fabric/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "rwa-fabric/metadata/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
