# RPI-DHCP-PTP-server
Przenośny serwer diagnostyczny DHCP i PTP

## Endpointy

### GET /dhcp_info

* dhcp_server_active - działamy jako server DHCP czy klient

* leases - lista leasów np. "10.0.0.139 e0:d5:5e:83:cd:13". null, gdy jest pusta lub działamy jako klient

* my_ip - stały adres IP, gdy działamy jako server lub adres przydzielony przez zewnętrzny server DHCP, null, gdy nie mamy adresu

### GET /ptp_info

* clock_count - liczba innych zegarów w sieci

* current_master - adres MAC zegara o roli master, jest to nasz adres MAC, jeżeli działamy jako master lub nie znaleziono obcego mastera

* current_offset - różnica pomiedzy czasem otrzymanym od mastera, a czasem lokalnym urządzenia, wartość użyteczna tylko w trybie slave

* current_time - czas otrzymany od mastera, gdy działamy w trybie slave lub czas lokalny urządzenia, który jest serwowany, gdy działamy w trybie master

* foreign_master - w trybie slave wskazuje czy wykryto obcego mastera, w trybie master jest nieużywana

* master_description - opis zegara master w formacie "Marka: Model", jeżeli zegar go nie posiada to null

* ptp_master_active - czy działamy w trybie master czy slave

### POST /dhcp_toggle

Zapytanie przełącza DHCP pomiędzy trybem klienta i serwera. Payload może być pusty.

### POST /ptp_toggle

Zapytanie przełącza PTP pomiędzy trybem master i slave. Payload może być pusty.

### POST /set_time

Ustawia czas lokalnego zegara urządzenia w celu serwowania go w trybie master PTP. Payload musi być type JSON z polem "time" zawierającym datę i czas w formacie ISO8601. Czas może zawierać część ułamkową sekundy oraz przesunięcie względem UTC.

### POST /sync_time

Synchronizuje czas lokalnego zegara z obcym masterem. Zapytanie działa tylko w trybie slave, gdy znaleziony został obcy master, w przeciwnym wypadku nic nie robi. Payload może być pusty.
