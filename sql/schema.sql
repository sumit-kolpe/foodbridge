-- FoodBridge - PostgreSQL schema (Milestone 2 approved DDL)
-- Run: psql -h <host> -U <user> -d <db> -f sql/schema.sql

DROP TABLE IF EXISTS Allocation;
DROP TABLE IF EXISTS RecipientRequest;
DROP TABLE IF EXISTS FoodDonation;
DROP TABLE IF EXISTS FoodCategory;
DROP TABLE IF EXISTS Organization;

CREATE TABLE Organization (
    organization_id SERIAL PRIMARY KEY,
    organization_name VARCHAR(150) NOT NULL,
    organization_type VARCHAR(20) NOT NULL
        CHECK (organization_type IN ('donor', 'recipient', 'both')),
    address TEXT,
    city VARCHAR(100),
    zip_code VARCHAR(15),
    contact_information VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active'
        CHECK (status IN ('active', 'inactive'))
);

CREATE TABLE FoodCategory (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    storage_type VARCHAR(30)
        CHECK (storage_type IN
        ('refrigerated', 'frozen', 'shelf-stable', 'other')),
    description TEXT
);

CREATE TABLE FoodDonation (
    donation_id BIGSERIAL PRIMARY KEY,
    donor_org_id INTEGER NOT NULL
        REFERENCES Organization(organization_id),
    category_id INTEGER NOT NULL
        REFERENCES FoodCategory(category_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    donated_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    pickup_deadline TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'available'
        CHECK (status IN
        ('available', 'partially_allocated', 'fully_allocated',
         'expired', 'cancelled')),
    CHECK (expires_at > donated_at),
    CHECK (pickup_deadline >= donated_at)
);

CREATE TABLE RecipientRequest (
    request_id BIGSERIAL PRIMARY KEY,
    recipient_org_id INTEGER NOT NULL
        REFERENCES Organization(organization_id),
    category_id INTEGER NOT NULL
        REFERENCES FoodCategory(category_id),
    requested_quantity INTEGER NOT NULL
        CHECK (requested_quantity > 0),
    requested_at TIMESTAMP NOT NULL,
    needed_by TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'open'
        CHECK (status IN
        ('open', 'partially_fulfilled', 'fulfilled',
         'expired', 'cancelled')),
    CHECK (needed_by >= requested_at)
);

CREATE TABLE Allocation (
    allocation_id BIGSERIAL PRIMARY KEY,
    donation_id BIGINT NOT NULL
        REFERENCES FoodDonation(donation_id),
    request_id BIGINT NOT NULL
        REFERENCES RecipientRequest(request_id),
    quantity_allocated INTEGER NOT NULL
        CHECK (quantity_allocated > 0),
    allocated_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN
        ('pending', 'confirmed', 'picked_up',
         'delivered', 'cancelled')),
    picked_up_at TIMESTAMP,
    delivered_at TIMESTAMP,
    CHECK (delivered_at IS NULL OR picked_up_at IS NOT NULL)
);
