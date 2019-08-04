# apustaja – Python3 Telegram-botti

### Laite- ja ohjelmistovaatimukset
Apustaja vaatii muutamia Python3-kirjastoja toimiakseen. Voit asentaa nämä esimerkiksi pip:n avulla seuraavalla komennolla, hyödyntäen reposta löytyvää `requirements.txt` tiedostoa:

**Linux/Mac**: Avaa terminal/bash shell -> `python3 -m pip install -r requirements.txt`

**Windows**: Avaa cmd.exe -> `python3` tai `python` -> `pip install -r requirements.txt`

- `holidays` kirjastoa tarvitaan pyhäpäivien huomioimiseen tukipäiviä laskettaessa.
- `telepot` on kirjasto joka kommunikoi Telegramin API:n kanssa.
- `gTTs` on Googlen tarjoama ilmainen text-to-speech muuntaja.
- `bs4` eli BeautifulSoup4 on kirjasto jota käytetään verkkosivujen html:n tonkimiseen, apustajan tapauksessa säätietojen hakemiseen `outside.aalto.fi` -sivustolta.
- `pydub` on kirjasto jolla muunnetaan äänitiedostoja formaatista toiseen. Apustajan tapauksessa `.mp3` -> `.ogg` `/tts`-komentoa ajettaessa, mikä on välttämätön muunnos jos viestit halutaan lähettää median sijaan ääniviesteinä.
- `ujson` on normaalin `json`-kirjaston korvaava, varsin suuria nopeutuksia tarjoava kirjasto json-tiedostojen purkamiseen.

---

### Käyttöönotto
Ensimmäistä kertaa ajettaessa ohjelma pyytää sekä Telegramin bot-API avainta sekä OpenWeatherMapin API-avainta `/saa`-komentoa varten. Botin API avaimen saat luomalla uuden botin, mikä hoituu lähettämällä viestin `@BotFather` botille Telegramissa. 

OpenWeatherMapin API-avain ei ole pakollinen (laita avaimeksi vaikka `000` jos et aio käyttää komentoa), mutta tämäkin on ilmainen ja sen voit hankkia openweathermap.org osoitteesta.

Kun olet saanut botin luotua, nappaa sen API-avain ja käynnistä botti komennolla `apustaja.py -start`.

---

### To-do
- settings.json -tiedoston siirtäminen yhdeksi .db tiedostoksi
- kaiken ryhmä- ja/tai käyttäjädatan poistaminen komennolla
- /s-komennon siirtäminen käyttämään sed-syntaksia

---

##### Komennot
**`/saa`** kertoo sään (oletuksena) Otaniemessä. 

- Lämpötila-, ilmanpaine- ja ilmankosteustiedot haetaan `outside.aalto.fi` -sivustolta, joka päivittyy tasaisin väliajoin. Muu data, kuten yleinen säätila (pilvisyys, sade, UV-indeksi) haetaan OpenWeatherMapin tarjoaman ilmaisen API:n avulla, johon tarvitset myös API-avaimen; tämän saat rekisteröitymällä ilmaiseksi oheisessa linkissä: https://home.openweathermap.org/users/sign_up

- Voit kutsua säätä muissa kaupungeissa lisäämällä kaupungin nimen komennon perään, esimerkiksi `/saa Helsinki`. Oletuskaupungin voit vaihtaa komennolla `/settings saa defaultCity`.

---

**[RIKKI] `/webcam`** hakee noin vartin välein päivittyvän tilannekuvan Aalto-yliopiston ylläpitämiltä, Väreelle päin suunnatuilta webkameroilta. Vaihtoehtoina joko `väre` tai `mt13`/`maarintie`, jolloin komento toimii esimerkiksi tyyliin `/webcam väre`. Otetut kuvat tallentuvat `/data/webcam` -kansioon, mutta kuvia ei säilytetä viimeisintä kuvaa enempää.

**Huom** Kuvat eivät ole päivittyneet Aallon palvelimille huhtikuusta alkaen, eli komennon lähettämät kuvat eivät enää muutu eikä kuvassa oleva kellonaika pidä paikkaansa.

---

**`/markov`** muodostaa (osittain) satunnaisen viestin Markov-ketjuilla. Komennolle on muutamia eri käyttömuotoja, jotka on listattu alla.

Huomioithan: luettuja viestejä ei tallenneta sellaisenaan, vaan niistä muodostetaan lennossa Markov-ketju, joka tallennetaan `chainStore.db` -tiedostoon. Tallennettuja viestejä ei siis suoranaisesti voi lukea, ellei kyseessä ole täysin uniikki viesti täysin uniikeilla sanoilla.

Tietokannan sarakkeet ovat seuraavanlaiset:

`[word1baseform]` | `[word1]` | `[word2]` | `[count]`

- `word1baseform` on tallennetun sanan "perusmuoto" joka auttaa lauseiden jatkamisessa luomalla saman muodon esim. erikoismerkkejä sisältäville sanoille (esim. `hei!` ja `hei?` omaisivat sanan perusmuodon `hei`).

- `word1` on ns. pääsana ja `word2` on pääsanan jälkeen esiintynyt sana. Jos sana on tyhjä, merkitsee se lauseen loppua. `count` tallentaa esiintymiskertojen määrän, jonka avulla ketju/viesti muodostetaan todennäköisyyspainotetusti.

Alla on listattu komennon käyttötavat:

- `/markov`: muodostaa viestin koko ryhmän viesteistä.

- `/markov [lause/sana]`: jatkaa annettua lausetta tai sanaa. Jos lausetta ei voi jatkaa, tuotetaan sen perään täysin annettuun kontekstiin liittymätöntä tekstiä.

- Voit myös jatkaa viestejä vastaamalla niihin `/markov`-komennolla.

---

**`/s`** -komennolla voit "korvata" tekstiä toisten henkilöiden viesteissä vastaamalla viestiin. Syntaksi on `/s teksti_jonka_haluat_korvata > teksti_jolla_haluat_sen_korvata`. Huomioithan, että komento on merkkikokoriippuvainen (case sensitive) tilanteissa joissa korvattava teksti löytyy: 

Viesti: `Da da Da da` -> `/s da > du` tuottaa tekstin `Da du Da du`. Toisaalta, jos komento olisi `Da Da Da` -> `/s da > du`, olisi tuotos `du du du`.

---

**`/tts`**

Yksinkertainen text-to-speech -komento, joka muuntaa tekstiä suomenkieliseksi ääneksi käyttäen Googlen gTTS-palvelua. Puheen kielen voi vaihtaa komennolla `/settings tts defaultLanguage`. Käyttötapoja on muutamia:

- `/tts [teksti]`: muuntaa annetun tekstin ääneksi.

- `/tts /markov`: muodostaa markov-ketjun ja muuntaa sen ääneksi. Voit myös antaa /markov -komennolle lisäargumentteja.

- `/tts` + vastaus viestiin: muuntaa viestin johon komennolla on vastattu ääneksi.

--

**`/wordcloud`**

Muodosta sanapilvi ryhmään lähetetyistä viesteistä. Käyttää samaa tietokantaa kuin /markov-komento, eli pilveä ei muodosteta tekstistä vaan sanojen esiintymistodennäköisyyksistä.

--

**`/tuet`**

Milloin opintotuki tulee? Ei toistaiseksi kerro asumistuen saapumispäivää.

--

**`/roll`**

Gettaa tuplat. Lisäargumentteina on myös /roll [kolikko] ja /roll [noppa].
