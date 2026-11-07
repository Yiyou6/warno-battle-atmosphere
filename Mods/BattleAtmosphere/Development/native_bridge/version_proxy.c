/* Reversible Windows loader entry: forward the game's VERSION imports to the
   actual System32 DLL. Initialize the mod outside DllMain on first API use. */
#include <windows.h>
#include <wchar.h>
#include <string.h>
typedef ULONG_PTR HCRYPTPROV, HCRYPTHASH, HCRYPTKEY;
typedef unsigned int ALG_ID;
#define PROV_RSA_AES 24
#define CRYPT_VERIFYCONTEXT 0xf0000000
#define CALG_SHA_256 0x800c
#define HP_HASHVAL 2

extern int ba_startup(void);
static HMODULE real_version;
static LONG started;
static LONG hash_checked;
static int hash_valid;
static int mod_enabled(void) {
    static const GUID saved_games={0x4c5c32ff,0xbb9d,0x43b0,{0xb5,0xb4,0x2d,0x72,0xe5,0x4e,0xaa,0xa4}};
    HMODULE shell=LoadLibraryW(L"shell32.dll"), ole=LoadLibraryW(L"ole32.dll");
    HRESULT (WINAPI *folder)(const GUID *,DWORD,HANDLE,wchar_t **);
    void (WINAPI *free_memory)(void *);
    wchar_t *saved=NULL, path[32768], list[4096], *part, *end;
    int enabled=0;
    if (!shell || !ole) goto done;
    folder=(void *)GetProcAddress(shell,"SHGetKnownFolderPath");
    free_memory=(void *)GetProcAddress(ole,"CoTaskMemFree");
    if (!folder || !free_memory || folder(&saved_games,0,NULL,&saved)<0 || !saved) goto done;
    if (wcslen(saved)>32000) {free_memory(saved);goto done;}
    wcscpy(path,saved);free_memory(saved);wcscat(path,L"\\EugenSystems\\WARNO\\mod\\Config.ini");
    GetPrivateProfileStringW(L"Config",L"ActivatedMods",L"",list,4096,path);
    part=list;
    while (*part && *part!=L';') {
        while (*part==L' ' || *part==L'|') part++;
        end=part;while (*end && *end!=L'|' && *end!=L';') end++;
        if (end-part==16 && !wcsncmp(part,L"BattleAtmosphere",16)) {enabled=1;break;}
        part=end;
    }
    if (enabled) {
        if (!GetModuleFileNameW(NULL,path,32768)) {enabled=0;goto done;}
        part=wcsrchr(path,L'\\');if (!part) {enabled=0;goto done;} *part=0;
        if (wcslen(path)>32000) {enabled=0;goto done;}
        wcscat(path,L"\\Mods\\BattleAtmosphere\\Runtime\\runtime.ini");
        enabled=GetPrivateProfileIntW(L"Runtime",L"Enabled",0,path)==1;
    }
done:
    if (shell) FreeLibrary(shell);if (ole) FreeLibrary(ole);
    return enabled;
}
static int exe_matches(void) {
    static const unsigned char expected[32] = {
        0x70,0xf3,0x4d,0x84,0x4e,0xbf,0x23,0xee,0xa9,0x2d,0x53,0x5f,0xad,0x0f,0xff,0xb6,
        0xe0,0xbc,0x60,0xdd,0x1f,0x64,0xcc,0x80,0xc2,0xb9,0x03,0xd0,0x6a,0xba,0xb3,0xa8};
    HMODULE api = LoadLibraryW(L"advapi32.dll");
    BOOL (WINAPI *acquire)(HCRYPTPROV *,LPCWSTR,LPCWSTR,DWORD,DWORD);
    BOOL (WINAPI *create)(HCRYPTPROV,ALG_ID,HCRYPTKEY,DWORD,HCRYPTHASH *);
    BOOL (WINAPI *update)(HCRYPTHASH,const BYTE *,DWORD,DWORD);
    BOOL (WINAPI *digest)(HCRYPTHASH,DWORD,BYTE *,DWORD *,DWORD);
    BOOL (WINAPI *destroy)(HCRYPTHASH);
    BOOL (WINAPI *release)(HCRYPTPROV,DWORD);
    HCRYPTPROV provider=0; HCRYPTHASH hash=0;
    HANDLE file=INVALID_HANDLE_VALUE;
    wchar_t path[32768]; unsigned char block[65536], output[32];
    DWORD read, size=32; int ok=0;
    if (!api) return 0;
    acquire=(void *)GetProcAddress(api,"CryptAcquireContextW");
    create=(void *)GetProcAddress(api,"CryptCreateHash");
    update=(void *)GetProcAddress(api,"CryptHashData");
    digest=(void *)GetProcAddress(api,"CryptGetHashParam");
    destroy=(void *)GetProcAddress(api,"CryptDestroyHash");
    release=(void *)GetProcAddress(api,"CryptReleaseContext");
    if (!acquire || !create || !update || !digest || !destroy || !release) goto done;
    if (!acquire(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT) || !create(provider,CALG_SHA_256,0,0,&hash)) goto done;
    if (!GetModuleFileNameW(NULL,path,32768)) goto done;
    file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if (file==INVALID_HANDLE_VALUE) goto done;
    for (;;) {
        if (!ReadFile(file,block,sizeof(block),&read,NULL)) goto done;
        if (!read) break;
        if (!update(hash,block,read,0)) goto done;
    }
    ok=digest(hash,HP_HASHVAL,output,&size,0) && size==32 && !memcmp(output,expected,32);
done:
    if (file!=INVALID_HANDLE_VALUE) CloseHandle(file);
    if (hash) destroy(hash);
    if (provider) release(provider,0);
    FreeLibrary(api);
    return ok;
}
static FARPROC resolve(const char *name) {
    wchar_t path[32768];
    if (InterlockedCompareExchange(&started,1,0)==0) {
        DWORD length=GetSystemDirectoryW(path,32700);
        if (length && length<32700) {
            wcscat(path,L"\\version.dll");
            real_version=LoadLibraryW(path);
        }
        InterlockedExchange(&started,2);
    }
    if (!real_version) {SetLastError(ERROR_MOD_NOT_FOUND);return NULL;}
    return GetProcAddress(real_version,name);
}
int ba_allowed(void) {
    if (!hash_checked) { hash_valid=exe_matches(); hash_checked=1; }
    if (!hash_valid) return 0;
    if (strstr(GetCommandLineA(),"BattleAtmosphereProbeAuto") && strstr(GetCommandLineA(),"-headless")) {
        char setting[8];
        if (GetEnvironmentVariableA("BA_VALIDATE_ACTIVATION",setting,8) && setting[0]=='1') return mod_enabled();
        return 1;
    }
    if (strstr(GetCommandLineA(),"-noMod") || strstr(GetCommandLineA(),"--local-path")) return 0;
    return mod_enabled();
}
#define FORWARD(ret,name,args,params) \
__declspec(dllexport) ret WINAPI name args { \
    typedef ret (WINAPI *Fn) args; Fn target=(Fn)resolve(#name); \
    if (!target) return 0; return target params; }
FORWARD(DWORD,GetFileVersionInfoSizeW,(LPCWSTR a,LPDWORD b),(a,b))
FORWARD(DWORD,GetFileVersionInfoSizeA,(LPCSTR a,LPDWORD b),(a,b))
FORWARD(BOOL,GetFileVersionInfoW,(LPCWSTR a,DWORD b,DWORD c,LPVOID d),(a,b,c,d))
FORWARD(BOOL,GetFileVersionInfoA,(LPCSTR a,DWORD b,DWORD c,LPVOID d),(a,b,c,d))
FORWARD(BOOL,VerQueryValueW,(const LPVOID a,LPWSTR b,LPVOID *c,PUINT d),(a,b,c,d))
FORWARD(BOOL,VerQueryValueA,(const LPVOID a,LPSTR b,LPVOID *c,PUINT d),(a,b,c,d))
FORWARD(DWORD,GetFileVersionInfoSizeExW,(DWORD a,LPCWSTR b,LPDWORD c),(a,b,c))
FORWARD(DWORD,GetFileVersionInfoSizeExA,(DWORD a,LPCSTR b,LPDWORD c),(a,b,c))
FORWARD(BOOL,GetFileVersionInfoExW,(DWORD a,LPCWSTR b,DWORD c,DWORD d,LPVOID e),(a,b,c,d,e))
FORWARD(BOOL,GetFileVersionInfoExA,(DWORD a,LPCSTR b,DWORD c,DWORD d,LPVOID e),(a,b,c,d,e))
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID reserved) {
    if (reason==DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        /* Minimal checked vtable installation only. Hash/file verification and
           Python are deferred to the native launcher outside loader lock. */
        ba_startup();
    }
    return TRUE;
}
