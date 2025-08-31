--
-- PostgreSQL database dump
--

\restrict xDjquAvwT5WkuNXGLUUYUIux5z3P7MtZF3QUEdVrhq16ti8Ee4Cl6Kbk3PeAsje

-- Dumped from database version 16.10
-- Dumped by pg_dump version 16.10

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: procurement_analysis_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.procurement_analysis_status AS ENUM (
    'PENDING_ANALYSIS',
    'ANALYSIS_IN_PROGRESS',
    'ANALYSIS_SUCCESSFUL',
    'ANALYSIS_FAILED'
);


ALTER TYPE public.procurement_analysis_status OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO postgres;

--
-- Name: file_records; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.file_records (
    id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    analysis_id integer NOT NULL,
    file_name character varying NOT NULL,
    gcs_path character varying NOT NULL,
    extension character varying,
    size_bytes integer NOT NULL,
    nesting_level integer NOT NULL,
    included_in_analysis boolean NOT NULL,
    exclusion_reason character varying,
    prioritization_logic character varying
);


ALTER TABLE public.file_records OWNER TO postgres;

--
-- Name: file_record_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.file_record_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.file_record_id_seq OWNER TO postgres;

--
-- Name: file_record_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.file_record_id_seq OWNED BY public.file_records.id;


--
-- Name: procurement_analyses; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.procurement_analyses (
    procurement_control_number character varying(255) NOT NULL,
    analysis_date timestamp with time zone DEFAULT now() NOT NULL,
    risk_score smallint,
    risk_score_rationale text,
    summary text,
    red_flags jsonb,
    warnings text[],
    document_hash character varying(64),
    original_documents_url character varying(1024),
    processed_documents_url character varying(1024),
    original_documents_gcs_path character varying,
    processed_documents_gcs_path character varying,
    analysis_id integer NOT NULL,
    version_number integer NOT NULL,
    estimated_cost numeric(12,6),
    status public.procurement_analysis_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.procurement_analyses OWNER TO postgres;

--
-- Name: procurement_analysis_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.procurement_analysis_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.procurement_analysis_id_seq OWNER TO postgres;

--
-- Name: procurement_analysis_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.procurement_analysis_id_seq OWNED BY public.procurement_analyses.analysis_id;


--
-- Name: procurements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.procurements (
    procurement_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    pncp_control_number character varying NOT NULL,
    proposal_opening_date timestamp with time zone,
    proposal_closing_date timestamp with time zone,
    object_description text NOT NULL,
    total_awarded_value double precision,
    is_srp boolean NOT NULL,
    procurement_year integer NOT NULL,
    procurement_sequence integer NOT NULL,
    pncp_publication_date timestamp with time zone NOT NULL,
    last_update_date timestamp with time zone NOT NULL,
    modality_id integer NOT NULL,
    procurement_status_id integer NOT NULL,
    total_estimated_value double precision,
    version_number integer NOT NULL,
    raw_data jsonb NOT NULL,
    content_hash character varying(64)
);


ALTER TABLE public.procurements OWNER TO postgres;

--
-- Name: procurement_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.procurement_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.procurement_id_seq OWNER TO postgres;

--
-- Name: procurement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.procurement_id_seq OWNED BY public.procurements.procurement_id;


--
-- Name: file_records id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.file_records ALTER COLUMN id SET DEFAULT nextval('public.file_record_id_seq'::regclass);


--
-- Name: procurement_analyses analysis_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.procurement_analyses ALTER COLUMN analysis_id SET DEFAULT nextval('public.procurement_analysis_id_seq'::regclass);


--
-- Name: procurements procurement_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.procurements ALTER COLUMN procurement_id SET DEFAULT nextval('public.procurement_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: file_records file_record_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.file_records
    ADD CONSTRAINT file_record_pkey PRIMARY KEY (id);


--
-- Name: procurement_analyses procurement_analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.procurement_analyses
    ADD CONSTRAINT procurement_analysis_pkey PRIMARY KEY (analysis_id);


--
-- Name: procurements procurement_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.procurements
    ADD CONSTRAINT procurement_pkey PRIMARY KEY (pncp_control_number, version_number);


--
-- Name: idx_analysis_pid_ver; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_analysis_pid_ver ON public.procurement_analyses USING btree (procurement_control_number, version_number);


--
-- Name: idx_analysis_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_analysis_status ON public.procurement_analyses USING btree (status);


--
-- Name: idx_procurement_analysis_pid_ver; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX idx_procurement_analysis_pid_ver ON public.procurement_analyses USING btree (procurement_control_number, version_number);


--
-- Name: idx_procurement_pid_ver; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_procurement_pid_ver ON public.procurements USING btree (pncp_control_number, version_number DESC);


--
-- Name: ix_document_hash; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_document_hash ON public.procurement_analyses USING btree (document_hash);


--
-- Name: ix_procurement_content_hash; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_procurement_content_hash ON public.procurements USING btree (content_hash);


--
-- Name: file_records file_record_analysis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.file_records
    ADD CONSTRAINT file_record_analysis_id_fkey FOREIGN KEY (analysis_id) REFERENCES public.procurement_analyses(analysis_id);


--
-- Name: procurement_analyses fk_procurement_version; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.procurement_analyses
    ADD CONSTRAINT fk_procurement_version FOREIGN KEY (procurement_control_number, version_number) REFERENCES public.procurements(pncp_control_number, version_number);


--
-- PostgreSQL database dump complete
--

\unrestrict xDjquAvwT5WkuNXGLUUYUIux5z3P7MtZF3QUEdVrhq16ti8Ee4Cl6Kbk3PeAsje
