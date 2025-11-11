--
-- PostgreSQL database dump
--

-- Dumped from database version 16.4 (Debian 16.4-1.pgdg120+1)
-- Dumped by pg_dump version 16.4 (Debian 16.4-1.pgdg120+1)

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: groups; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.groups (
    id integer NOT NULL,
    name character varying
);


ALTER TABLE public.groups OWNER TO marakoris;

--
-- Name: groups_id_seq; Type: SEQUENCE; Schema: public; Owner: marakoris
--

CREATE SEQUENCE public.groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.groups_id_seq OWNER TO marakoris;

--
-- Name: groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: marakoris
--

ALTER SEQUENCE public.groups_id_seq OWNED BY public.groups.id;


--
-- Name: payments; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.payments (
    id integer NOT NULL,
    "user" integer,
    payment_system character varying,
    amount double precision,
    data timestamp without time zone
);


ALTER TABLE public.payments OWNER TO marakoris;

--
-- Name: payments_id_seq; Type: SEQUENCE; Schema: public; Owner: marakoris
--

CREATE SEQUENCE public.payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.payments_id_seq OWNER TO marakoris;

--
-- Name: payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: marakoris
--

ALTER SEQUENCE public.payments_id_seq OWNED BY public.payments.id;


--
-- Name: person_promocode_association; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.person_promocode_association (
    promocode_id integer,
    users_id integer
);


ALTER TABLE public.person_promocode_association OWNER TO marakoris;

--
-- Name: promocode; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.promocode (
    id integer NOT NULL,
    text character varying NOT NULL,
    add_balance integer NOT NULL
);


ALTER TABLE public.promocode OWNER TO marakoris;

--
-- Name: promocode_id_seq; Type: SEQUENCE; Schema: public; Owner: marakoris
--

CREATE SEQUENCE public.promocode_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.promocode_id_seq OWNER TO marakoris;

--
-- Name: promocode_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: marakoris
--

ALTER SEQUENCE public.promocode_id_seq OWNED BY public.promocode.id;


--
-- Name: servers; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.servers (
    id integer NOT NULL,
    name character varying NOT NULL,
    type_vpn integer NOT NULL,
    outline_link character varying,
    ip character varying NOT NULL,
    connection_method boolean,
    panel character varying,
    inbound_id integer,
    password character varying,
    vds_password character varying,
    login character varying,
    work boolean,
    space integer,
    "group" character varying
);


ALTER TABLE public.servers OWNER TO marakoris;

--
-- Name: servers_id_seq; Type: SEQUENCE; Schema: public; Owner: marakoris
--

CREATE SEQUENCE public.servers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.servers_id_seq OWNER TO marakoris;

--
-- Name: servers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: marakoris
--

ALTER SEQUENCE public.servers_id_seq OWNED BY public.servers.id;


--
-- Name: static_persons; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.static_persons (
    id integer NOT NULL,
    name character varying,
    server integer
);


ALTER TABLE public.static_persons OWNER TO marakoris;

--
-- Name: static_persons_id_seq; Type: SEQUENCE; Schema: public; Owner: marakoris
--

CREATE SEQUENCE public.static_persons_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.static_persons_id_seq OWNER TO marakoris;

--
-- Name: static_persons_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: marakoris
--

ALTER SEQUENCE public.static_persons_id_seq OWNED BY public.static_persons.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.users (
    id integer NOT NULL,
    tgid bigint,
    banned boolean,
    notion_oneday boolean,
    subscription bigint,
    balance integer,
    username character varying,
    fullname character varying,
    referral_user_tgid bigint,
    referral_balance integer,
    lang character varying,
    lang_tg character varying,
    server integer,
    "group" character varying
);


ALTER TABLE public.users OWNER TO marakoris;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: marakoris
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO marakoris;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: marakoris
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: withdrawal_requests; Type: TABLE; Schema: public; Owner: marakoris
--

CREATE TABLE public.withdrawal_requests (
    id integer NOT NULL,
    amount integer NOT NULL,
    payment_info character varying NOT NULL,
    communication character varying,
    check_payment boolean,
    user_tgid bigint
);


ALTER TABLE public.withdrawal_requests OWNER TO marakoris;

--
-- Name: withdrawal_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: marakoris
--

CREATE SEQUENCE public.withdrawal_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.withdrawal_requests_id_seq OWNER TO marakoris;

--
-- Name: withdrawal_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: marakoris
--

ALTER SEQUENCE public.withdrawal_requests_id_seq OWNED BY public.withdrawal_requests.id;


--
-- Name: groups id; Type: DEFAULT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.groups ALTER COLUMN id SET DEFAULT nextval('public.groups_id_seq'::regclass);


--
-- Name: payments id; Type: DEFAULT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.payments ALTER COLUMN id SET DEFAULT nextval('public.payments_id_seq'::regclass);


--
-- Name: promocode id; Type: DEFAULT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.promocode ALTER COLUMN id SET DEFAULT nextval('public.promocode_id_seq'::regclass);


--
-- Name: servers id; Type: DEFAULT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.servers ALTER COLUMN id SET DEFAULT nextval('public.servers_id_seq'::regclass);


--
-- Name: static_persons id; Type: DEFAULT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.static_persons ALTER COLUMN id SET DEFAULT nextval('public.static_persons_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: withdrawal_requests id; Type: DEFAULT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.withdrawal_requests ALTER COLUMN id SET DEFAULT nextval('public.withdrawal_requests_id_seq'::regclass);


--
-- Data for Name: groups; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.groups (id, name) FROM stdin;
\.


--
-- Data for Name: payments; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.payments (id, "user", payment_system, amount, data) FROM stdin;
1	3	Telegram Stars	150	2024-08-07 15:52:11.392644
2	2	CryptoBot	150	2024-08-09 07:50:48.952561
3	7	Telegram Stars	150	2024-08-11 22:17:30.03981
4	1	Telegram Stars	150	2024-08-13 11:36:37.173415
5	1	Telegram Stars	150	2024-08-13 12:29:18.785382
6	4	Telegram Stars	150	2024-08-13 15:02:33.052524
7	87	YooKassaSmart	150	2024-08-14 04:29:25.868258
8	2	YooKassaSmart	150	2024-08-14 11:47:20.212124
9	34	YooKassaSmart	390	2024-08-14 16:32:39.996901
10	36	YooKassaSmart	150	2024-08-15 09:25:45.776174
11	121	YooKassaSmart	150	2024-08-16 03:07:35.151811
12	113	YooKassaSmart	150	2024-08-16 11:27:17.811758
13	128	YooKassaSmart	800	2024-08-16 13:20:05.568059
14	118	YooKassaSmart	390	2024-08-17 15:30:44.214347
15	129	YooKassaSmart	150	2024-08-18 14:28:03.782665
16	141	YooKassaSmart	390	2024-08-20 18:55:31.324141
17	230	YooKassaSmart	150	2024-08-24 12:10:40.248272
18	247	YooKassaSmart	390	2024-08-30 03:36:03.074876
19	253	YooKassaSmart	150	2024-08-30 21:48:32.476711
20	59	YooKassaSmart	150	2024-09-03 17:42:52.150627
21	266	YooKassaSmart	150	2024-09-04 17:51:56.821763
22	268	YooKassaSmart	150	2024-09-05 07:43:08.462485
23	282	YooKassaSmart	150	2024-09-06 07:29:54.757374
24	61	YooKassaSmart	150	2024-09-07 13:35:33.664121
25	284	YooKassaSmart	150	2024-09-07 21:20:42.936238
26	282	YooKassaSmart	390	2024-09-08 03:28:01.177008
27	87	YooKassaSmart	150	2024-09-11 15:59:57.372421
28	315	YooKassaSmart	150	2024-09-11 19:38:07.083126
\.


--
-- Data for Name: person_promocode_association; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.person_promocode_association (promocode_id, users_id) FROM stdin;
\.


--
-- Data for Name: promocode; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.promocode (id, text, add_balance) FROM stdin;
\.


--
-- Data for Name: servers; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.servers (id, name, type_vpn, outline_link, ip, connection_method, panel, inbound_id, password, vds_password, login, work, space, "group") FROM stdin;
20	Узбекистан Outline	0	{"apiUrl":"https://194.113.153.106:26982/pxEowvTHc5g0HsTqTifQ2A","certSha256":"59640B21CA8752F170DAD3567381D63F62F1EAD9E2BB166FFC47169BD1BF4488"}	194.113.153.106	\N	\N	\N	\N	s7jbfpxE6SK389UZQ3	\N	t	10	\N
24	Россия Outline	0	{"apiUrl":"https://185.239.50.235:31976/yVHGyiaEMrE2Qb7GjoWx4A","certSha256":"ED24C8A6EBD796448A164A1624937456C4528BFDE8BD25876727EC040B55B0AC"}	185.239.50.235	\N	\N	\N	\N	r7h30WgEBvI67JTjh5	\N	t	4	\N
25	Россия Vless	1	\N	185.239.50.235:5555	f	sanaei	1	Feowiuerjfwe143	r7h30WgEBvI67JTjh5	marakoris	t	4	\N
15	Германия ShadowSocs	2	\N	185.233.81.238:5555	f	sanaei	2	vKxBl9OTan	arn9NwX5099M	marakoris	t	6	\N
13	Германия Outline	0	{"apiUrl":"https://185.233.81.238:40768/VHTRYMcKRbly0nABAL9ZUg","certSha256":"3FADE8F08F7CDA14983ABEC6969BF747743DC722EAFC1D801284C9600FEE7447"}	185.233.81.238	\N	\N	\N	\N	arn9NwX5099M	\N	t	16	\N
14	Германия Vless	1	\N	185.233.81.238:5555	f	sanaei	1	vKxBl9OTan	arn9NwX5099M	marakoris	t	12	\N
22	Узбекистан Shadow	2	\N	194.113.153.106:5555	f	sanaei	2	o83zc7GbUe	s7jbfpxE6SK389UZQ3	marakoris	t	1	\N
21	Узбекистан Vless	1	\N	194.113.153.106:5555	f	sanaei	1	o83zc7GbUe	s7jbfpxE6SK389UZQ3	marakoris	t	5	\N
\.


--
-- Data for Name: static_persons; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.static_persons (id, name, server) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.users (id, tgid, banned, notion_oneday, subscription, balance, username, fullname, referral_user_tgid, referral_balance, lang, lang_tg, server, "group") FROM stdin;
5	5253491050	t	f	1723382488	0	@None	Ольга	\N	0	ru	\N	\N	\N
6	276833266	t	f	1723398028	0	@Leefort	Илья	\N	0	ru	\N	\N	\N
8	149448413	t	f	1723446013	0	@c0r75z	Алексей	\N	0	ru	\N	\N	\N
9	1474529975	t	f	1723451024	0	@None	Михайлович	\N	0	ru	\N	\N	\N
10	452613245	t	f	1723453424	0	@WeBoot	Vadim	\N	0	ru	\N	\N	\N
11	6315553436	t	f	1723463432	0	@VIKTOP5858	Viktor Topilin	\N	0	ru	\N	\N	\N
12	206277926	t	f	1723474226	0	@None	Dmitriy	\N	0	ru	\N	\N	\N
14	6149659422	t	f	1723524832	0	@None	Александи	\N	0	ru	\N	\N	\N
15	5170545926	t	f	1723525282	0	@chatlanin70	Сергей Данилоха	\N	0	ru	\N	\N	\N
16	5240282182	t	f	1723529587	0	@None	Мария Тимирова	\N	0	ru	\N	\N	\N
17	7204580166	t	f	1723545865	0	@None	52138	\N	0	ru	\N	\N	\N
19	6973410090	t	f	1723561720	0	@None	Галина	\N	0	ru	\N	\N	\N
20	6593181760	t	f	1723562350	0	@JONIEL100	Renat	\N	0	ru	\N	\N	\N
21	6729904324	t	f	1723566030	0	@Eltnmiw	.	\N	0	ru	\N	\N	\N
22	5220749810	t	f	1723569855	0	@Am_onka	Кто то	\N	0	ru	\N	\N	\N
23	713339047	t	f	1723574133	0	@ertoxxx	qwerty	\N	0	ru	\N	\N	\N
24	784469867	t	f	1723611393	0	@None	Bloody Frenzy	\N	0	ru	\N	\N	\N
25	5243667416	t	f	1723612143	0	@None	Александр Лебедев	\N	0	ru	\N	\N	\N
26	7108317408	t	f	1723614003	0	@aaandrey23	Андрей	\N	0	ru	\N	\N	\N
27	6436101832	t	f	1723616944	0	@Polin_thik	Polin_Thik128💋	\N	0	ru	\N	\N	\N
28	6666726748	t	f	1723626267	0	@None	Дима	\N	0	ru	\N	\N	\N
29	500065728	t	f	1723626627	0	@professor_50	Эдуард	\N	0	ru	\N	\N	\N
30	776227938	t	f	1723628562	0	@V1tyaV1tya	Vitya Vitya	\N	0	ru	\N	\N	\N
31	7093896564	t	f	1723630482	0	@None	79046602483	\N	0	ru	\N	\N	\N
32	6696677368	t	f	1723636971	0	@None	Круассанчик	\N	0	ru	\N	\N	\N
33	5397194852	t	f	1723640046	0	@None	Алексей Некозырев	\N	0	ru	\N	\N	\N
122	6553763401	t	f	1724011311	0	@Bear_mos	🐻	\N	0	ru	ru	\N	\N
36	608605345	f	f	1726392359	0	@Mila1902	Людмила	\N	0	ru	\N	14	\N
58	2132334648	t	f	1723714731	0	@mis_slin	Карелия	\N	0	ru	\N	\N	\N
1	323843168	f	t	1726216650	150	@ARL1KIN	A.R.L.I.K.I.N	\N	0	ru	\N	\N	\N
60	6084064063	t	f	1723716996	0	@garag_mlt	ГАРАЖ	\N	0	ru	\N	\N	\N
128	462832230	f	f	1740143646	0	@ArchNext	Arthur	\N	0	ru	ru	14	\N
69	1300325707	t	f	1723730136	0	@None	Юрий Дмитриевич	\N	0	ru	\N	\N	\N
125	5927197111	t	f	1724033538	0	@None	Владимир	\N	0	ru	ru	\N	\N
141	5162347758	f	t	1732285722	0	@None	Aleksey Shichalin	221883650	0	ru	ru	20	\N
132	5257704471	t	f	1724085259	0	@None	Марат	\N	0	ru	ru	\N	\N
35	1044685414	t	f	1723652934	0	@VITAlii_2020	АЛЕКСЕЙ Ша	\N	0	ru	\N	\N	\N
37	1061645434	t	f	1723652935	0	@Saturn_mrt	Дарья Мартыненко	\N	0	ru	\N	\N	\N
38	661739204	t	f	1723652936	0	@Oksana_kik_ps	Оксана *	\N	0	ru	\N	\N	\N
119	6937480976	t	f	1723984938	0	@None	Александр	\N	0	ru	ru	\N	\N
135	5721862669	t	f	1724158264	0	@None	Alexander	\N	0	ru	ru	\N	\N
129	454178949	f	t	1726755895	0	@s5gear2	lenintakoimolodoy	\N	0	ru	ru	15	\N
4	5873672289	f	t	1726228993	0	@TopStepShop	Top Step	\N	0	ru	\N	21	\N
39	5951928133	t	f	1723654971	0	@None	А М	\N	0	ru	\N	\N	\N
40	1236441141	t	f	1723655287	0	@acc4deal	Egor Commercial	\N	0	ru	\N	\N	\N
41	2023161143	t	f	1723657582	0	@Offilla	offi#книжныйчервь	\N	0	ru	\N	\N	\N
42	356321176	t	f	1723659232	0	@None	Oleg Rom	\N	0	ru	\N	\N	\N
43	176593069	t	f	1723659397	0	@zhendos_bandos	Zhenya	\N	0	ru	\N	\N	\N
44	357749225	t	f	1723659577	0	@None	Nikolay Vasilev	\N	0	ru	\N	\N	\N
45	1604890022	t	f	1723661978	0	@Igor198325	Игорь Легков	\N	0	ru	\N	\N	\N
180	6041373997	t	f	1724503144	0	@None	Sus Kuk	\N	0	ru	ru	\N	\N
3	5826176899	f	f	1726341803	0	@Friend_Admin	Friend Admin 👨‍💼	\N	0	ru	\N	\N	\N
7	1755803856	t	f	1726082280	0	@proseccovich	𝒟𝒶𝓋𝒾𝒹	\N	0	ru	\N	\N	\N
138	7195154544	t	f	1724197113	0	@None	Людмилла	\N	0	ru	ru	\N	\N
54	202018378	t	f	1723712766	0	@whataboutsonya	sonya m	\N	0	ru	\N	\N	\N
218	5183484175	t	f	1724619498	0	@kivi_ro	Karina	\N	0	ru	en	\N	\N
144	5605988510	f	t	1724259796	0	@None	Елена	\N	0	ru	ru	15	\N
13	93725391	f	t	1726153440	0	@sir_Dallas	Dmitriy V	\N	0	ru	\N	\N	\N
2	870499087	f	t	1728652843	0	@marakoris	Maksim Zhelezkin	\N	0	ru	\N	14	\N
62	187380313	f	f	1731493383	0	@Viktor_SPB	Viktor	\N	0	ru	\N	24	\N
177	6673758818	t	f	1724496033	0	@None	Ваня Ваня	\N	0	ru	ru	\N	\N
185	1963705486	t	f	1724515053	0	@ami_sha456	Amina	\N	0	ru	ru	\N	\N
165	1735173440	t	f	1724426598	0	@None	Виктория	\N	0	ru	ru	\N	\N
168	2058819573	t	f	1724438764	0	@alicewfx	Aliciss🎀💕💪	\N	0	ru	ru	\N	\N
147	1948352414	t	f	1724265408	0	@m20242424	🎇	\N	0	ru	ru	\N	\N
150	5803620296	t	f	1724308053	0	@None	Виталий	\N	0	ru	ru	\N	\N
153	5973638283	t	f	1724327569	0	@None	?	\N	0	ru	ru	\N	\N
18	405248793	f	t	1726397385	0	@just5fun	Oleg Kosarev	\N	0	ru	\N	13	\N
171	6670717220	t	f	1724445318	0	@None	Динара	\N	0	ru	ru	\N	\N
156	1734931414	t	f	1724391333	0	@None	Magen	\N	0	ru	ru	\N	\N
162	2024353785	t	f	1724415649	0	@cand1sto7m	конфетный	\N	0	ru	ru	\N	\N
204	2145072060	t	f	1724582253	0	@None	Den	\N	0	ru	ru	\N	\N
55	5155355797	t	f	1723713667	0	@None	Vladimir	\N	0	ru	\N	\N	\N
56	5945778908	t	f	1723713996	0	@Niko120r	niko 💀	\N	0	ru	\N	\N	\N
57	5130269023	t	f	1723714656	0	@None	Людмила	\N	0	ru	\N	\N	\N
61	458619780	f	f	1728394588	0	@garsoncheckfri	Alexander	\N	0	ru	\N	13	\N
63	7398994306	t	f	1723717446	0	@s5497sn	владимир солдаткин	\N	0	ru	\N	\N	\N
64	6681705119	t	f	1723717746	0	@None	Сейран Арсланов	\N	0	ru	\N	\N	\N
65	6559138903	t	f	1723717911	0	@berzdog69	berzdog69	\N	0	ru	\N	\N	\N
66	2041260681	t	f	1723720761	0	@None	Славик Славик	\N	0	ru	\N	\N	\N
67	867338809	t	f	1723723011	0	@kostyamez	Костя Андреевич	\N	0	ru	\N	\N	\N
130	801253625	t	f	1724077639	0	@ALIZA6999	Лиза	\N	0	ru	ru	\N	\N
68	5973329418	t	f	1723730137	0	@ew99ph3	чиназес"🪬#похитительницатрусовдрейка #дкпикми#дисапикми#руспикми	\N	0	ru	\N	\N	\N
70	1839636635	t	f	1723733226	0	@tteennshi	пиво¿🚩	\N	0	ru	\N	\N	\N
71	5857800365	t	f	1723733751	0	@None	Мария Латышенко	\N	0	ru	\N	\N	\N
72	1513098660	t	f	1723735431	0	@None	тушинов соел	\N	0	ru	\N	\N	\N
73	6961315727	t	f	1723736841	0	@None	Перчик007	\N	0	ru	\N	\N	\N
74	1713868929	t	f	1723737081	0	@fa3nat_anime	Monkey. D. Luffy	\N	0	ru	\N	\N	\N
116	873836576	t	f	1723912128	0	@None	Юлия Головина	\N	0	ru	ru	\N	\N
75	5842756417	t	f	1723740906	0	@None	АЛЕКСАНДР	\N	0	ru	\N	\N	\N
76	6342130641	t	f	1723743606	0	@None	Владимир	\N	0	ru	\N	\N	\N
77	5610368118	t	f	1723751256	0	@None	Миша	\N	0	ru	\N	\N	\N
46	1462601458	t	f	1723675521	0	@TheDaycareAttendant1	Art of Horror	\N	0	ru	\N	\N	\N
47	1743519745	t	f	1723677546	0	@W_E_G_W_E_G	…	\N	0	ru	\N	\N	\N
48	7249427729	t	f	1723684386	0	@None	Вячеслав	\N	0	ru	\N	\N	\N
59	730864896	f	f	1728065752	0	@Usov_art	Паша	\N	0	ru	\N	13	\N
49	444720718	t	f	1723689831	0	@sima5500	Сергей	\N	0	ru	\N	\N	\N
166	1197753453	t	f	1724433498	0	@wassup_white	Сергеев	\N	0	ru	ru	\N	\N
80	2054788899	t	f	1723783116	0	@fluteln	lin	\N	0	ru	\N	\N	\N
120	5066783498	t	f	1723990593	0	@None	Сергей Ровнейко	\N	0	ru	ru	\N	\N
50	1480158114	t	f	1723700901	0	@Annihilator25	Александр(Lancelot)	\N	0	ru	\N	\N	\N
51	468225666	t	f	1723702716	0	@None	Artem Sushko	\N	0	ru	\N	\N	\N
52	930798502	t	f	1723710711	0	@Buzon06	SssRrr	\N	0	ru	\N	\N	\N
53	6896829075	t	f	1723711371	0	@None	Денис	\N	0	ru	\N	\N	\N
84	170242228	t	f	1723799541	0	@Sasha_FromRasha	Alexander	\N	0	ru	\N	\N	\N
86	479533913	t	f	1723800066	0	@SPB_Anna_Khusainova	Andy Borderline	\N	0	ru	\N	\N	\N
91	6126550255	t	f	1723815796	0	@None	Olegnikolaev..	\N	0	ru	\N	\N	\N
133	7178857539	t	f	1724143113	0	@None	Малиль Канаметов	\N	0	ru	ru	\N	\N
97	5539447678	t	f	1723826448	0	@None	Павел	\N	0	ru	\N	\N	\N
104	1665741237	t	f	1723835613	0	@IvanSokolov777	Ivan 2022🎧 Sokolov	\N	0	ru	\N	\N	\N
105	929263395	t	f	1723842468	0	@None	Bogdan	\N	0	ru	\N	\N	\N
107	533936327	t	f	1723866453	0	@DeadlySin19	Сергей	\N	0	ru	\N	\N	\N
110	2042579676	t	f	1723879218	0	@Col224	I Loki	\N	0	ru	\N	\N	\N
112	5741038884	t	f	1723881139	0	@None	Вовчик	\N	0	ru	\N	\N	\N
114	5916661514	t	f	1723892778	0	@None	garri	\N	0	ru	\N	\N	\N
188	6656299408	t	f	1724523813	0	@None	Виктор Долбунов	\N	0	ru	ru	\N	\N
142	1313458097	t	f	1724252298	0	@None	Roman Roman	\N	0	ru	ru	\N	\N
123	5630525804	t	f	1724015268	0	@None	юсти	\N	0	ru	ru	\N	\N
126	1418874900	t	f	1724057028	0	@Goydaban	Слава	415700563	0	ru	ru	\N	\N
154	5126907831	t	f	1724339568	0	@Stas1630	Станислав	\N	0	ru	ru	\N	\N
136	5948220354	t	f	1724163528	0	@Batya_Cristhofer	￴￴￴￴￴￴￴	\N	0	ru	ru	\N	\N
181	344202354	t	f	1724503968	0	@VAlex_CS	Alex	\N	0	ru	ru	\N	\N
160	6998168762	t	f	1724407595	0	@None	Елена	\N	0	ru	ru	\N	\N
139	1919561186	t	f	1724240166	0	@None	Александр	\N	0	ru	en	\N	\N
163	7170119418	t	f	1724421874	0	@None	Устрица 🦪	\N	0	ru	ru	\N	\N
190	952104092	t	f	1724527668	0	@fellonovv	𝙁𝙚𝙡𝙡𝙤𝙣𝙤𝙫𝙫 🦴	\N	0	ru	ru	\N	\N
145	6942533735	t	f	1724262468	0	@None	Игорь Макаров	\N	0	ru	ru	\N	\N
192	5834517156	t	f	1724534103	0	@Svetljac	Сvетлана	\N	0	ru	ru	\N	\N
148	2006357090	t	f	1724268093	0	@None	Елена	\N	0	ru	ru	\N	\N
169	6267813591	t	f	1724443128	0	@Ponvvvv	PONVИОꟼ	\N	0	ru	ru	\N	\N
196	1348908660	t	f	1724541093	0	@Hbbsis6	Надежда Скачёк	\N	0	ru	ru	\N	\N
198	265894471	t	f	1724557803	0	@None	Artem Stigeev	\N	0	ru	ru	\N	\N
194	1078633744	t	f	1724540043	0	@KyzyaaaaA	Антон Васильевич	\N	0	ru	ru	\N	\N
199	419095506	t	f	1724566728	0	@Crittt	Maxim	\N	0	ru	ru	\N	\N
178	6662090603	t	f	1724496963	0	@wiskkasxx	😜	\N	0	ru	ru	\N	\N
186	285620583	t	f	1724516883	0	@ne_kroshka_enod	🧩	\N	0	ru	ru	\N	\N
172	840812593	t	f	1724461383	0	@None	lara	\N	0	ru	ru	\N	\N
34	415700563	f	f	1732206776	0	@sator_io	Сатор	\N	0	ru	\N	20	\N
175	6944427628	t	f	1724487333	0	@None	Хуй Тебе	\N	0	ru	ru	\N	\N
202	1243534837	t	f	1724578729	0	@AlicaLancraft	Alica Lancraft	\N	0	ru	ru	\N	\N
89	5144821449	t	f	1723805376	0	@None	Lilyusya	\N	0	ru	\N	\N	\N
90	6793139826	t	f	1723807221	0	@None	Ghost1988 Ghost1988	\N	0	ru	\N	\N	\N
118	228290668	f	t	1732006898	0	@st3p4	Степан	\N	0	ru	en	13	\N
92	5331074472	t	f	1723820583	0	@None	Маруся Корабухина	\N	0	ru	\N	\N	\N
134	2083055675	t	f	1724156344	0	@salikov91	Юрий Саликов	\N	0	ru	ru	\N	\N
117	720143245	t	f	1723969128	0	@Stannislaff	Stannislaff	\N	0	ru	ru	\N	\N
152	6615410140	t	f	1724313513	0	@None	Ольга	\N	0	ru	ru	\N	\N
140	5064405652	t	f	1724246163	0	@None	Филиппов Михаил	\N	0	ru	ru	\N	\N
164	6726342601	t	f	1724426269	0	@MImimimigas	Mimimi	\N	0	ru	ru	\N	\N
78	1073349693	t	f	1723754541	0	@pasha_revnost	Павел Тихомиров	\N	0	ru	\N	\N	\N
79	6381280208	t	f	1723775976	0	@Boroda1962	Борисыч	\N	0	ru	\N	\N	\N
93	1371546871	t	f	1723821798	0	@None	Никола Никола	\N	0	ru	\N	\N	\N
94	5339296361	t	f	1723822878	0	@k_a_t_y_a1109	Катюша♡︎	\N	0	ru	\N	\N	\N
121	951571674	f	f	1726687902	0	@None	Сергей Шевченко	\N	0	ru	ru	15	\N
81	350538545	t	f	1723789326	0	@theballin	Роман	\N	0	ru	\N	\N	\N
82	1130465610	t	f	1723793406	0	@maclenchik	маша	\N	0	ru	\N	\N	\N
143	970130277	t	f	1724256034	0	@None	Николай	\N	0	ru	ru	\N	\N
83	5939794793	t	f	1723796646	0	@None	Ирина	\N	0	ru	\N	\N	\N
85	6197992897	t	f	1723799546	0	@None	Jurassic	\N	0	ru	\N	\N	\N
95	5241015993	t	f	1723824993	0	@NIKITAWOOD	Никита твой босс Босс	\N	0	ru	\N	\N	\N
124	5248940165	t	f	1724018403	0	@SBBoytsov	Сергей	\N	0	ru	ru	\N	\N
88	7069735513	t	f	1723802256	0	@None	11ⁿ58	\N	0	ru	\N	\N	\N
137	5151127922	t	f	1724170938	0	@NEGRNEGRNERN	Бабайка	\N	0	ru	ru	\N	\N
96	418587338	t	f	1723825413	0	@promiteymedia	Илья Алексеевич	\N	0	ru	\N	\N	\N
98	6609801505	t	f	1723827618	0	@None	Леонид	\N	0	ru	\N	\N	\N
99	5422158377	t	f	1723827783	0	@burimov_s1	Sergei Burimov	\N	0	ru	\N	\N	\N
100	631984164	t	f	1723828683	0	@DS693082	diss	\N	0	ru	\N	\N	\N
101	5500143002	t	f	1723831458	0	@Pavel9992	Павел	\N	0	ru	\N	\N	\N
102	7040343056	t	f	1723832223	0	@None	DiOkSa	\N	0	ru	\N	\N	\N
103	5336995947	t	f	1723832230	0	@Wey_Shaw785	Ваня	\N	0	ru	\N	\N	\N
106	472940559	t	f	1723864488	0	@tugrik1983	Вован	\N	0	ru	\N	\N	\N
108	533478622	t	f	1723869648	0	@AsyaVelichko	Ася	\N	0	ru	\N	\N	\N
109	5225410507	t	f	1723875378	0	@None	сергей	\N	0	ru	\N	\N	\N
111	1232634236	t	f	1723880598	0	@None	Ярый	\N	0	ru	\N	\N	\N
193	307476227	t	f	1724534179	0	@smithy0104	Vlad	\N	0	ru	en	\N	\N
115	1763255049	t	f	1723893963	0	@Ratislav71181	Огнеславъ Перунов	\N	0	ru	\N	\N	\N
200	5164681026	t	f	1724567163	0	@None	Елена Мащенко	\N	0	ru	ru	\N	\N
127	1623303531	t	f	1724062353	0	@the1datr	Anton Kuzmenko	\N	0	ru	ru	\N	\N
113	221883650	f	t	1726828660	0	@flabbylawn	Алексей Поляков	\N	39	ru	\N	20	\N
155	6407077433	t	f	1724381718	0	@taraxican	Selmons🦴	\N	0	ru	en	\N	\N
131	1537519996	t	f	1724083473	0	@None	Sss	\N	0	ru	ru	\N	\N
197	5682940759	t	f	1724553018	0	@AlekseyB05	Алексей	\N	0	ru	ru	\N	\N
201	641261401	t	f	1724574813	0	@mitenkoellii	𝓔𝓵𝓲𝓷𝓪	\N	0	ru	ru	\N	\N
157	1570636299	t	f	1724392594	0	@None	мигель родригес	\N	0	ru	ru	\N	\N
205	5837773965	t	f	1724583093	0	@unsaintedcuster	Miranda Chichikova 🧪	\N	0	ru	ru	\N	\N
187	7324696889	t	f	1725731682	0	@None	Саша	\N	0	ru	ru	\N	\N
146	6810159785	t	f	1724265363	0	@None	Александр	\N	0	ru	ru	\N	\N
149	5880335868	t	f	1724268619	0	@Kmd_75	Михаил Котельников	\N	0	ru	ru	\N	\N
151	1700737344	t	f	1724308353	0	@None	Виктор	\N	0	ru	ru	\N	\N
206	5283945884	t	f	1724586198	0	@None	Аленчик	\N	0	ru	ru	\N	\N
161	6147477957	f	t	1724409431	0	@None	Роман Беляев	\N	0	ru	ru	15	\N
207	1109718105	t	f	1724588269	0	@ssonnexx	соня	\N	0	ru	ru	\N	\N
182	941612670	t	f	1724510239	0	@rnyntdnv	💜	\N	0	ru	ru	\N	\N
184	1212145880	t	f	1724514003	0	@amwaaazeerv	софийская.	\N	0	ru	ru	\N	\N
210	7493160070	t	f	1724602518	0	@None	Dmitriy.L Dmitriy.L	\N	0	ru	ru	\N	\N
158	1006394570	t	f	1724398608	0	@None	Сергей Ш	\N	0	ru	ru	\N	\N
159	6395207958	t	f	1724405809	0	@None	Сказо4ник	\N	0	ru	ru	\N	\N
208	6173215269	t	f	1724598709	0	@dkozakov	Dmitry Kozakov	\N	0	ru	en	\N	\N
209	1770844804	t	f	1724602159	0	@anyaa_rs	аня	\N	0	ru	ru	\N	\N
191	5090010607	t	f	1724531733	0	@Viticha	Виктор🌹	\N	0	ru	ru	\N	\N
170	6583715534	t	f	1724444059	0	@AEEEAEeea	AE	\N	0	ru	ru	\N	\N
195	5133175546	t	f	1724540809	0	@NeDDzzz	NeDz	\N	0	ru	ru	\N	\N
173	1288851391	t	f	1724472904	0	@Ilya_Arnautov	Илья Арнаутов	\N	0	ru	ru	\N	\N
176	6672382981	t	f	1724487903	0	@None	Мария	\N	0	ru	ru	\N	\N
203	6066337967	t	f	1724580874	0	@talakan55	PapaJon38	\N	0	ru	ru	\N	\N
179	5500926388	t	f	1724500503	0	@motobratishka59	Moto Brother	\N	0	ru	ru	\N	\N
189	6729345133	t	f	1724524578	0	@None	.	\N	0	ru	ru	\N	\N
167	5295722025	t	f	1724436799	0	@abrikos777777	Саша	\N	0	ru	ru	\N	\N
211	7142786099	t	f	1724603793	0	@RybalkoGosha	Гоша	\N	0	ru	ru	\N	\N
212	1442872672	t	f	1724605293	0	@None	D_b0biss_n	\N	0	ru	ru	\N	\N
213	6877616604	t	f	1724610829	0	@Mr_Frst1	MR.FROST1K	\N	0	ru	ru	\N	\N
214	5194166237	t	f	1724611234	0	@None	Tostem	\N	0	ru	ru	\N	\N
215	6183437764	t	f	1724611249	0	@montanaasdx	Yeat_Vinchi	\N	0	ru	ru	\N	\N
216	306837107	t	f	1724612088	0	@None	Екатерина Прокофьева	\N	0	ru	ru	\N	\N
217	1454232611	t	f	1724618569	0	@Demi_Tattoo	Сергей Шульга	\N	0	ru	ru	\N	\N
87	1543301436	f	t	1729156969	0	@None	Alexander35109	\N	0	ru	\N	20	\N
233	5894151067	t	f	1724767829	0	@Difrisk	Диана Птицелов	\N	0	ru	ru	\N	\N
234	6914506492	t	f	1724771614	0	@None	Ahmadi Ramin	\N	0	en	en	\N	\N
235	5898688711	t	f	1724775980	0	@stas_delivery	stas_delivery	\N	0	ru	ru	\N	\N
249	492972391	t	f	1725108758	0	@ArtyFlash	𝕱𝖑𝖆𝖘𝖍	\N	0	ru	ru	\N	\N
236	5033032118	t	f	1724777813	0	@G_O_U_S_Tim	Иван	\N	0	ru	ru	\N	\N
174	739280569	t	f	1724474553	0	@None	Дима Красников	\N	0	ru	ru	\N	\N
237	5981466216	t	f	1724780088	0	@None	Галина	\N	0	ru	ru	\N	\N
247	517981671	f	t	1733057052	0	@None	63130 Сергей	\N	0	ru	ru	13	\N
219	6570747284	t	f	1724628633	0	@None	precious	\N	0	ru	ru	\N	\N
220	5523448340	t	f	1724629098	0	@None	Bruh	\N	0	ru	ru	\N	\N
221	6739750611	t	f	1724633013	0	@None	Людмила Валеева	\N	0	ru	en	\N	\N
246	6769049820	t	f	1724999628	0	@None	Stas Choban	\N	0	ru	ru	\N	\N
238	2071489094	t	f	1724799446	0	@BorisovOlegVladimirovich	Oleg Borisov	\N	0	ru	ru	\N	\N
222	345616992	t	f	1724657764	0	@None	Юрий	\N	0	ru	ru	\N	\N
183	5139628257	t	f	1724511379	0	@polarsystem711	ᵖᵒᶫᵃʳ ˢʸˢ ♡ ᵃˢᵏ ᵖʳᶰˢ 🍖🌈•🌸🌙	\N	0	ru	ru	\N	\N
223	1417884168	t	f	1724660944	0	@kots_stacie	.Kavun.	\N	0	ru	be	\N	\N
230	5756521237	f	f	1727377295	0	@Ptitselow	Вячеслав	\N	0	ru	ru	14	\N
239	332015756	t	f	1724802068	0	@Hamidreza_Nasirian2023	Hamidreza Nasirian	\N	0	en	en	\N	\N
263	1440500745	t	f	1725375490	0	@Gventee	Гарман Гарман	\N	0	ru	ru	\N	\N
224	6176501990	t	f	1724663044	0	@None	_♡ ○_𝗖𝐡ⲣùꫛҜ_○ ♡_	\N	0	ru	ru	\N	\N
256	6742473534	t	f	1725312669	0	@kz777_LLL	join	\N	0	ru	ru	\N	\N
240	5697005961	t	f	1724861493	0	@hlyupin	Антон Хлюпин	\N	0	ru	ru	\N	\N
241	6419160293	t	f	1724870900	0	@Egor_3427	Игорь	\N	0	ru	ru	\N	\N
225	5689626718	t	f	1724667469	0	@None	Заур	\N	0	ru	ru	\N	\N
226	7027641214	t	f	1724668908	0	@None	Светлана Свирина	\N	0	ru	ru	\N	\N
227	5716922517	t	f	1724669493	0	@None	34 Jaguar	\N	0	ru	ru	\N	\N
242	6810002027	t	f	1724878150	0	@None	Лили	\N	0	ru	ru	\N	\N
253	148891062	f	t	1727817082	0	@lazary	Лазарь	\N	0	ru	ru	21	\N
257	1634316549	t	f	1725324112	0	@ggg_li5	Weesx	\N	0	ru	ru	\N	\N
270	5942895698	t	f	1725459278	0	@wnawDbiQ	Артём	\N	0	ru	ru	\N	\N
228	5679550798	t	f	1724694138	0	@None	Анатолий Максись	\N	0	ru	ru	\N	\N
229	7026008370	t	f	1724696554	0	@None	Dzyankei Buzmakov	\N	0	ru	ru	\N	\N
258	5968321636	t	f	1725340128	0	@Muxammad_Paxriddinov_off	Muxammad	\N	0	ru	ru	\N	\N
231	5430372252	t	f	1724738134	0	@TREIDER_SHADOW	SHADOW	\N	0	ru	ru	\N	\N
232	270458090	t	f	1724759812	0	@demarkel	Dmitry	\N	0	ru	en	\N	\N
261	5613156339	t	f	1725358233	0	@hrltxs	аня	\N	0	ru	ru	\N	\N
250	580420859	t	f	1725133564	0	@vinsvova	Владимир	\N	0	ru	ru	\N	\N
279	1132856241	t	f	1725732703	0	@dashagrush	Дарья	\N	0	ru	ru	\N	\N
251	878197002	t	f	1725135543	0	@glebal	Паша Калинин	\N	0	ru	ru	\N	\N
243	6659477688	t	f	1724918134	0	@None	Сергей	\N	0	ru	ru	\N	\N
244	996055878	t	f	1724920279	0	@anatolog	Anatolog Anatolog🦴	\N	0	ru	ru	\N	\N
245	1985816302	t	f	1724924722	0	@None	Виктор	\N	0	ru	ru	\N	\N
252	1124730960	t	f	1725137984	0	@None	ЕЛЕНА	\N	0	ru	ru	\N	\N
248	1474162288	t	f	1725102635	0	@asyamee	асечка	\N	0	ru	en	\N	\N
264	1081835942	t	f	1725376819	0	@None	@Костя	\N	0	ru	ru	\N	\N
265	6749004944	t	f	1725379504	0	@VitekFFgg	Витек	\N	0	ru	ru	\N	\N
259	1508199478	t	f	1725342063	0	@None	Игорь	\N	0	ru	ru	\N	\N
254	1175275758	t	f	1725221303	0	@None	Gali Irina	\N	0	ru	ru	\N	\N
283	7009970940	t	f	1725873925	0	@None	Aleks Yandov	\N	0	ru	ru	\N	\N
262	620075051	t	f	1725372799	0	@anyadulcimer	Anya Zykova	\N	0	ru	ru	\N	\N
284	192164808	f	f	1728585088	0	@Adrenalin75	Руслан Кособоков	\N	0	ru	ru	20	\N
255	6570289055	t	f	1725305858	0	@None	GAN GAN	\N	0	ru	ru	\N	\N
260	1278346939	t	f	1725347795	0	@None	Михаил Шуршалин	\N	0	ru	ru	\N	\N
271	945413176	t	f	1725470511	0	@mira8berry	Мira Berry	415700563	0	ru	ru	\N	\N
273	858343260	t	f	1725483169	0	@shy001	Shy	\N	0	ru	ru	\N	\N
267	5444021202	t	f	1725435559	0	@None	Egor	\N	0	ru	ru	\N	\N
268	74034176	f	f	1728200611	0	@mr_reptiloid	В : Р	\N	0	ru	ru	13	\N
269	1983643971	t	f	1725454912	0	@None	HECTER	\N	0	ru	ru	\N	\N
275	6024554672	t	f	1725644629	0	@ARISTOCRAT675	Samurai	\N	0	ru	ru	\N	\N
272	6419104848	t	f	1725477754	0	@muzaffar546	M.G.Z.G	\N	0	ru	ru	\N	\N
274	5178242981	t	f	1725547975	0	@StalCraftop1gg	T R I P L E R	\N	0	ru	ru	\N	\N
280	366080699	t	f	1725767809	0	@vodoley61	vodoley	\N	0	ru	ru	\N	\N
266	5338676624	f	f	1728150930	0	@None	Олег Войнов	\N	0	ru	ru	24	\N
281	6382533947	t	f	1725823286	0	@wladosik12	Денис Стасюк	\N	0	ru	ru	\N	\N
278	1357336581	t	f	1725729874	0	@ivanovdenis_spb	Denis Iva	\N	0	ru	en	\N	\N
276	746634823	t	f	1725650390	0	@ForeverLiverpool	𝐋.𝐅.𝐂.	\N	0	ru	ru	\N	\N
277	1180644747	t	f	1725716022	0	@SuccessCargoCompany	Svetlana	\N	0	ru	ru	\N	\N
282	5677805308	f	t	1736565531	0	@USNext	US next	\N	0	ru	ru	20	\N
309	276518927	f	f	1726266009	0	@ffarzadnazari	farzad	\N	0	ru	en	\N	\N
310	7468047067	f	f	1726289351	0	@Ozzy7465	Ozzy McClung	\N	0	ru	en	\N	\N
290	449682179	t	f	1726038034	0	@None	Николай	\N	0	ru	ru	\N	\N
291	805721999	t	f	1726039474	0	@cherniy61	Cherniy	\N	0	ru	ru	\N	\N
292	5587554029	t	f	1726043166	0	@Spieler1000	$piel€r	\N	0	ru	de	\N	\N
293	5332415834	t	f	1726044679	0	@raidnnxx	Гдз по английскому языку	\N	0	ru	en	\N	\N
311	1621751260	f	f	1726306018	0	@OffOnli	GG	\N	0	ru	ru	14	\N
302	746032271	f	t	1726221020	0	@kolosochek_anastasia	Настя	\N	0	ru	ru	\N	\N
312	648564647	f	f	1726320375	0	@dumbab	Orki حبك	\N	0	ru	ru	21	\N
313	5452441162	f	f	1726322748	0	@waiifu_a	анютка	\N	0	ru	en	\N	\N
320	5811710312	f	f	1726392123	0	@None	Алеша Ярославце	\N	0	ru	ru	14	\N
294	6671789029	t	f	1726069623	0	@Guy4ik	Гай Геворков	\N	0	ru	ru	\N	\N
285	6368768339	t	f	1725931789	0	@None	Сережа Иванов	\N	0	ru	ru	\N	\N
314	5251988131	f	f	1726331870	0	@None	32078 Марина	\N	0	ru	ru	25	\N
297	583410710	t	f	1726136089	0	@art_bulat	Артур	\N	0	ru	ru	\N	\N
303	7361932448	f	t	1726225648	0	@yaroslavkorotchik	Ярослав Коротчик	\N	0	ru	en	\N	\N
286	1188253080	t	f	1725970061	0	@EeeKrytaya228	♡ ♡	\N	0	ru	ru	\N	\N
287	7447678036	t	f	1725973773	0	@None	Татьяна Викторовна	\N	0	ru	ru	\N	\N
304	7267156115	f	f	1726234024	0	@None	BARDOLO BARDOLO	\N	0	ru	id	\N	\N
295	5239595518	t	f	1726074009	0	@None	Вячеслав Каменских	\N	0	ru	ru	\N	\N
305	213666266	f	f	1726234975	0	@Chekomazov	Gennady Chekomazov	\N	0	ru	ru	\N	\N
306	6034943703	f	f	1726240870	0	@None	Рома Цухишвили	\N	0	ru	ru	14	\N
298	7286921320	f	t	1726165593	0	@None	Лол Лол	\N	0	ru	ru	15	\N
307	376043441	f	f	1726244326	0	@OlegArbitr	UralArbitr	\N	0	ru	ru	\N	\N
288	5001855018	t	f	1725994403	0	@PlaggFurina	Plagg	\N	0	ru	ru	\N	\N
308	918694603	f	f	1726254002	0	@dielez0	dielez	\N	0	ru	ru	13	\N
289	1183173587	t	f	1726001108	0	@Devilkaulitz	Devil Kaulitz	\N	0	ru	ru	\N	\N
316	464180877	f	f	1726342723	0	@prostopanda95	V. K.	\N	0	ru	ru	\N	\N
315	812935768	f	f	1729020600	0	@varvara_aksen	Varvara	\N	0	ru	ru	13	\N
296	1325943538	t	f	1726092738	0	@antonadilov	Антон Адилов	\N	0	ru	ru	\N	\N
317	570783798	f	f	1726353871	0	@kuznenix	Дмитрий Кузнецов	\N	0	ru	ru	14	\N
318	1484560324	f	f	1726373494	0	@sanek0870	Сергей Иванов	\N	0	ru	ru	\N	\N
299	114918905	f	t	1726206219	0	@chislov3d	chislov3d	\N	0	ru	ru	14	\N
300	214088075	f	t	1726214079	0	@gor_gades	Igor Zvezdny	\N	0	ru	ru	\N	\N
319	944051911	f	f	1726389395	0	@advisor_tg	Артём | Адвизор	\N	0	ru	ru	\N	\N
301	694690916	f	t	1726218574	0	@kk2eley	Ярослав Коротчик	\N	0	ru	en	15	\N
\.


--
-- Data for Name: withdrawal_requests; Type: TABLE DATA; Schema: public; Owner: marakoris
--

COPY public.withdrawal_requests (id, amount, payment_info, communication, check_payment, user_tgid) FROM stdin;
\.


--
-- Name: groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: marakoris
--

SELECT pg_catalog.setval('public.groups_id_seq', 1, false);


--
-- Name: payments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: marakoris
--

SELECT pg_catalog.setval('public.payments_id_seq', 28, true);


--
-- Name: promocode_id_seq; Type: SEQUENCE SET; Schema: public; Owner: marakoris
--

SELECT pg_catalog.setval('public.promocode_id_seq', 1, false);


--
-- Name: servers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: marakoris
--

SELECT pg_catalog.setval('public.servers_id_seq', 25, true);


--
-- Name: static_persons_id_seq; Type: SEQUENCE SET; Schema: public; Owner: marakoris
--

SELECT pg_catalog.setval('public.static_persons_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: marakoris
--

SELECT pg_catalog.setval('public.users_id_seq', 320, true);


--
-- Name: withdrawal_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: marakoris
--

SELECT pg_catalog.setval('public.withdrawal_requests_id_seq', 1, false);


--
-- Name: groups groups_name_key; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_name_key UNIQUE (name);


--
-- Name: groups groups_pkey; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_pkey PRIMARY KEY (id);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: promocode promocode_pkey; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.promocode
    ADD CONSTRAINT promocode_pkey PRIMARY KEY (id);


--
-- Name: promocode promocode_text_key; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.promocode
    ADD CONSTRAINT promocode_text_key UNIQUE (text);


--
-- Name: servers servers_name_key; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.servers
    ADD CONSTRAINT servers_name_key UNIQUE (name);


--
-- Name: servers servers_outline_link_key; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.servers
    ADD CONSTRAINT servers_outline_link_key UNIQUE (outline_link);


--
-- Name: servers servers_pkey; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.servers
    ADD CONSTRAINT servers_pkey PRIMARY KEY (id);


--
-- Name: static_persons static_persons_name_key; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.static_persons
    ADD CONSTRAINT static_persons_name_key UNIQUE (name);


--
-- Name: static_persons static_persons_pkey; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.static_persons
    ADD CONSTRAINT static_persons_pkey PRIMARY KEY (id);


--
-- Name: person_promocode_association uq_users_promocode; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.person_promocode_association
    ADD CONSTRAINT uq_users_promocode UNIQUE (promocode_id, users_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_tgid_key; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_tgid_key UNIQUE (tgid);


--
-- Name: withdrawal_requests withdrawal_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.withdrawal_requests
    ADD CONSTRAINT withdrawal_requests_pkey PRIMARY KEY (id);


--
-- Name: ix_groups_id; Type: INDEX; Schema: public; Owner: marakoris
--

CREATE INDEX ix_groups_id ON public.groups USING btree (id);


--
-- Name: ix_payments_id; Type: INDEX; Schema: public; Owner: marakoris
--

CREATE INDEX ix_payments_id ON public.payments USING btree (id);


--
-- Name: ix_promocode_id; Type: INDEX; Schema: public; Owner: marakoris
--

CREATE INDEX ix_promocode_id ON public.promocode USING btree (id);


--
-- Name: ix_servers_id; Type: INDEX; Schema: public; Owner: marakoris
--

CREATE INDEX ix_servers_id ON public.servers USING btree (id);


--
-- Name: ix_static_persons_id; Type: INDEX; Schema: public; Owner: marakoris
--

CREATE INDEX ix_static_persons_id ON public.static_persons USING btree (id);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: marakoris
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_withdrawal_requests_id; Type: INDEX; Schema: public; Owner: marakoris
--

CREATE INDEX ix_withdrawal_requests_id ON public.withdrawal_requests USING btree (id);


--
-- Name: payments payments_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_user_fkey FOREIGN KEY ("user") REFERENCES public.users(id);


--
-- Name: person_promocode_association person_promocode_association_promocode_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.person_promocode_association
    ADD CONSTRAINT person_promocode_association_promocode_id_fkey FOREIGN KEY (promocode_id) REFERENCES public.promocode(id) ON DELETE CASCADE;


--
-- Name: person_promocode_association person_promocode_association_users_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.person_promocode_association
    ADD CONSTRAINT person_promocode_association_users_id_fkey FOREIGN KEY (users_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: servers servers_group_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.servers
    ADD CONSTRAINT servers_group_fkey FOREIGN KEY ("group") REFERENCES public.groups(name) ON DELETE SET NULL;


--
-- Name: static_persons static_persons_server_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.static_persons
    ADD CONSTRAINT static_persons_server_fkey FOREIGN KEY (server) REFERENCES public.servers(id) ON DELETE SET NULL;


--
-- Name: users users_group_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_group_fkey FOREIGN KEY ("group") REFERENCES public.groups(name) ON DELETE SET NULL;


--
-- Name: users users_server_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_server_fkey FOREIGN KEY (server) REFERENCES public.servers(id) ON DELETE SET NULL;


--
-- Name: withdrawal_requests withdrawal_requests_user_tgid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: marakoris
--

ALTER TABLE ONLY public.withdrawal_requests
    ADD CONSTRAINT withdrawal_requests_user_tgid_fkey FOREIGN KEY (user_tgid) REFERENCES public.users(tgid);


--
-- PostgreSQL database dump complete
--

