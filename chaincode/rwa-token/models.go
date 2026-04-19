package main

import "time"

type AssetStatus string
type AssetType string

const (
	StatusActif      AssetStatus = "ACTIF"
	StatusGele       AssetStatus = "GELE"
	StatusEnEmission AssetStatus = "EN_EMISSION"
	StatusRembourse  AssetStatus = "REMBOURSE"
)

const (
	TypeObligation     AssetType = "OBLIGATION"
	TypeOPCVM          AssetType = "OPCVM"
	TypeImmobilier     AssetType = "IMMOBILIER"
	TypeDerive         AssetType = "DERIVE"
	TypeMatiere        AssetType = "MATIERE_PREMIERE"
	TypePrivateEquity  AssetType = "PRIVATE_EQUITY"
	TypeInfrastructure AssetType = "INFRASTRUCTURE"
)

type ProvenanceRecord struct {
	TxID          string    `json:"txID"`
	Timestamp     time.Time `json:"timestamp"`
	ActorMSP      string    `json:"actorMSP"`
	ActorDN       string    `json:"actorDN"`
	Action        string    `json:"action"`
	FromOwner     string    `json:"fromOwner"`
	ToOwner       string    `json:"toOwner"`
	Amount        float64   `json:"amount"`
	Justification string    `json:"justification"`
	BlockNumber   uint64    `json:"blockNumber"`
}

type FinancialAsset struct {
	AssetID        string             `json:"assetID"`
	ISIN           string             `json:"isin"`
	AssetType      AssetType          `json:"assetType"`
	AssetName      string             `json:"assetName"`
	IssuerMSP      string             `json:"issuerMSP"`
	IssuerLEI      string             `json:"issuerLEI"`
	CurrentOwner   string             `json:"currentOwner"`
	NominalValue   float64            `json:"nominalValue"`
	CurrentValue   float64            `json:"currentValue"`
	Currency       string             `json:"currency"`
	Status         AssetStatus        `json:"status"`
	IssuanceDate   string             `json:"issuanceDate"`
	MaturityDate   string             `json:"maturityDate"`
	CouponRate     float64            `json:"couponRate"`
	RatingMoodys   string             `json:"ratingMoodys"`
	FrozenBy       string             `json:"frozenBy"`
	FrozenAt       string             `json:"frozenAt"`
	FrozenReason   string             `json:"frozenReason"`
	RegulatoryRef  string             `json:"regulatoryRef"`
	TotalTransfers int                `json:"totalTransfers"`
	Provenance     []ProvenanceRecord `json:"provenance"`
}

type TransferRequest struct {
	AssetID       string  `json:"assetID"`
	ToOwner       string  `json:"toOwner"`
	Price         float64 `json:"price"`
	Justification string  `json:"justification"`
}
