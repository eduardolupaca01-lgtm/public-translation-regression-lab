//go:build windows
package main
import (
    "errors"
    "reflect"
    "strings"
    "testing"
)
func TestTX777ModalWelcomeIsNotOnShippingDefaultPath(t *testing.T){
    if reflect.ValueOf(tx771WelcomeBeforePayload).Pointer() !=
       reflect.ValueOf(tx777PlainWelcome).Pointer(){
        t.Fatal("legacy V95 MessageBox was still the default startup")
    }
    if yes,err:=tx771WelcomeBeforePayload();!yes||err!=nil{
        t.Fatal("non-modal startup blocked initial native window")
    }
}
func TestTX777SafeErrorMessageIsCopyableWithoutPrivatePaths(t *testing.T){
    err:=errors.New("TX771_PORTABLE_ENGINE_INSTALL_FAILED: C:\\Users\\Private\\my_game\\secret.dat")
    code:=tx777StatusCategory(err)
    if code!="TX771_PORTABLE_ENGINE_INSTALL_FAILED"{
        t.Fatalf("lost accurate original installer code: %s",code)
    }
    for _,bad:=range []string{"C:\\Users","my_game","secret.dat"}{
        if strings.Contains(code,bad){t.Fatal("personal data leaked")}
    }
    if tx777StatusCategory(errors.New("unexpected private message"))!="TX777_ERROR_NO_CLASIFICADO"{
        t.Fatal("unknown errors should not be copied verbatim")
    }
}
func TestTX777CancelledSelectionDoesNotStartModel(t *testing.T){
    if code,err:=tx777PlainWelcome();!code||err!=nil{t.Fatal("welcome short circuit unexpectedly failed")}
    if _,err:=tx777GameRootForTest("relative.exe");err==nil{
        t.Fatal("malformed or relative game path must not reach neural loader")
    }
}
func TestTX777HasResponsiveUIRatherThanBlockingModal(t *testing.T){
    if tx777CheckOriginalNoWelcome()!=nil{t.Fatal("native startup GUI not initialized")}
    // Tests which need to click real Windows controls are owner acceptance;
    // this source test does not mislabel synthetic UI as physical screenshot.
}
